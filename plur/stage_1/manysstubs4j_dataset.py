# Copyright 2021 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Classes for converting the ManySStuBs4J dataset to a PLUR dataset."""
import json
import os

import apache_beam as beam
import javalang
from plur.stage_1.plur_dataset import Configuration
from plur.stage_1.plur_dataset import PlurDataset
from plur.utils.graph_to_output_example import GraphToOutputExample
from plur.utils.graph_to_output_example import GraphToOutputExampleNotValidError
import unidiff


class ManySStuBs4JDataset(PlurDataset):
  """Converting data from manysstubs4j dataset to a PLUR dataset.

  The dataset is generated by: Karampatsis, Rafael-Michael, and Charles Sutton.
  'How Often Do Single-Statement Bugs Occur? The ManySStuBs4J Dataset.' arXiv
  preprint arXiv:1905.13334 (2019).

  There is no task associated with this dataset, so we use this dataset to
  create our own task. The task is to predict the bug fix transformation given
  the source code snippet.

  The dataset contains patches in unified diff format, and labels such as
  'Change Identifier Used' and 'Wrong Function Name'. First, we use unidiff
  library to get the code snippet before and after the change. We consider the
  code snippet before the change to be buggy and use the corresponding label.
  The code snippet after the change is considered to be bug free. Then, we use
  javalang to tokenize the code snippet. The input graph is a chain of source
  code tokens connected by 'NEXT_TOKEN' edges. And the output is a class label,
  which can be 'Change Identifier Used' or 'Wrong Function Name' when there is a
  bug. Or 'NO_BUG' when there is no bug.
  """

  # pylint: disable=line-too-long
  _URLS = {
      'sstubs.json': {
          'url': 'https://zenodo.org/record/3653444/files/sstubs?download=1',
          'sha1sum': '7217be8c154878c563820f53f7a5eacf6ac9c17a',
      }
  }
  _URLS_LARGE = {
      'sstubsLarge.json': {
          'url': 'https://zenodo.org/record/3653444/files/sstubsLarge?download=1',
          'sha1sum': 'c0bfd241a3fb60e84b39a8e2a1db2975f7c2be83',
      }
  }
  # pylint: enable=line-too-long
  _GIT_URL = {}
  _DATASET_NAME = 'manysstubs4j_dataset'
  _DATASET_DESCRIPTION = """\
  From GitHub README:

  The ManySStuBs4J corpus is a collection of simple fixes to Java bugs,
  designed for evaluating program repair techniques. We collect all
  bug-fixing changes using the SZZ heuristic[1], and then filter these to obtain
  a data set of small bug fix changes. These are single statement fixes,
  classified where possible into one of 16 syntactic templates which we call
  SStuBs. The dataset contains simple statement bugs mined from open-source
  Java projects hosted in GitHub. There are two variants of the dataset.
  One mined from the 100 Java Maven Projects and one mined from the top 1000
  Java Projects. The projects can be found in
  https://zenodo.org/record/3653444#.X2n3GowvND8. A project's popularity is
  determined by computing the sum of z-scores of its forks and watchers. We kept
  only bug commits that contain only single statement changes and ignore
  stylistic differences such as spaces or empty as well as differences in
  comments. Some single statement changes can be caused by refactorings, like
  changing a variable name rather than bug fixes. We attempted to detect and
  exclude refactorings such as variable, function, and class renamings, function
  argument renamings or changing the number of arguments in a function. The
  commits are classified as bug fixes or not by checking if the commit message
  contains any of a set of predetermined keywords such as bug, fix, fault etc.

  [1]: Śliwerski, Jacek, Thomas Zimmermann, and Andreas Zeller. 'When do changes
  induce fixes?.' ACM sigsoft software engineering notes 30.4 (2005): 1-5.
  """

  def __init__(self,
               stage_1_dir,
               configuration: Configuration = Configuration(),
               transformation_funcs=(),
               filter_funcs=(),
               user_defined_split_range=(80, 10, 10),
               num_shards=1000,
               seed=0,
               use_large_dataset=False,
               deduplicate=False):
    self.use_large_dataset = use_large_dataset
    if self.use_large_dataset:
      urls = self._URLS_LARGE
    else:
      urls = self._URLS
    super().__init__(
        self._DATASET_NAME,
        urls,
        self._GIT_URL,
        self._DATASET_DESCRIPTION,
        stage_1_dir,
        transformation_funcs=transformation_funcs,
        filter_funcs=filter_funcs,
        user_defined_split_range=user_defined_split_range,
        num_shards=num_shards,
        seed=seed,
        configuration=configuration,
        deduplicate=deduplicate)

  def download_dataset(self):
    """Download the dataset using requests."""
    super().download_dataset_using_requests()

  def get_all_raw_data_paths(self):
    """Get paths to all raw data."""
    if self.use_large_dataset:
      json_filename = os.path.join(self.raw_data_dir, 'sstubsLarge.json')
    else:
      json_filename = os.path.join(self.raw_data_dir, 'sstubs.json')
    return [json_filename]

  def raw_data_paths_to_raw_data_do_fn(self):
    """Returns a beam.DoFn subclass that reads the raw data."""
    # manysstubs4j does not define any data split, therefore we check if
    # user_defined_split_range is defined.
    assert bool(self.user_defined_split_range)
    return JsonExtractor(super().get_random_split)

  def raw_data_to_graph_to_output_example(self, raw_data):
    """Convert raw data to the unified GraphToOutputExample data structure.

    We create a node for each source code token and connect all nodes as a chain
    with 'NEXT_TOKEN' edges. The output is the bug type as a class.

    Args:
      raw_data: A dictionary with 'split', 'token' and 'label' as keys. The
        value of the 'split' field is the split (train/valid/test) that the data
        belongs to. The value of the 'token' field tokens of the code snippet.
        The value of the 'label' split is the bug type of the raw data.

    Raises:
      GraphToOutputExampleNotValidError if the GraphToOutputExample is not
      valid.

    Returns:
      A dictionary with keys 'split' and 'GraphToOutputExample'. Values are the
      split(train/validation/test) the data belongs, and the
      GraphToOutputExample instance.
    """
    split = raw_data['split']
    tokens = raw_data['tokens']
    label = raw_data['label']
    graph_to_output_example = GraphToOutputExample()

    # The nodes are the source code tokens
    for index, (token_type, token_value) in enumerate(tokens):
      graph_to_output_example.add_node(index, token_type, token_value)

    # We connect the nodes as a chain with the 'NEXT_TOKEN' edge between
    # each consecutive source code token node.
    for i in range(len(graph_to_output_example.get_nodes()) - 1):
      graph_to_output_example.add_edge(i, i+1, 'NEXT_TOKEN')

    # The output is the label.
    graph_to_output_example.add_class_output(label)

    for transformation_fn in self.transformation_funcs:
      graph_to_output_example = transformation_fn(graph_to_output_example)

    if not graph_to_output_example.check_if_valid():
      raise GraphToOutputExampleNotValidError(
          'Invalid GraphToOutputExample found {}'.format(
              graph_to_output_example))

    for filter_fn in self.filter_funcs:
      if not filter_fn(graph_to_output_example):
        graph_to_output_example = None
        break

    return {'split': split, 'GraphToOutputExample': graph_to_output_example}


class JsonExtractor(beam.DoFn):
  """Class to read the manysstubs4j data, and transform them into tokens."""

  def __init__(self, random_split_fn):
    self.random_split_fn = random_split_fn

  def _patch_to_source_and_target_tokens(self, patch_str):
    """Tokenize source code before and after the change.

    We get the code snippet before and after change from the patch. And then
    tokenize them.

    Args:
      patch_str: A string containing a patch in unified diff format.

    Returns:
      Two lists, the first list contains code tokens before the change. The
      second list contains code tokens after the change.
    """
    # Parse the patch using unidiff.
    patch = unidiff.PatchSet(patch_str)
    # len(patch) is the number of changed files in the patch, len(patch[0])
    # is the number of changed hunks in the first file. Since patches in
    # manysstubs4j are changing a single statement, we are guaranteed to have
    # a single file and a single hunk. Therefore patch[0][0].source contains
    # the code snippet before the change.
    # We used line[1:] here because the character is either a whitespace for
    # non-changed lines, or '+'/'-' for changed lines.
    source = ''.join([line[1:] for line in patch[0][0].source])
    target = ''.join([line[1:] for line in patch[0][0].target])

    # Try to tokenize the code snippet, if we failed, return two empty lists.
    try:
      source_tokens = []
      for token in javalang.tokenizer.tokenize(source):
        source_tokens.append((type(token).__name__, token.value))

      target_tokens = []
      for token in javalang.tokenizer.tokenize(target):
        target_tokens.append((type(token).__name__, token.value))

      return source_tokens, target_tokens
    except javalang.tokenizer.LexerError:
      return [], []

  def _raw_data_dict_generator(self, json_file_reader):
    """Function to parse json data from a file reader, and yield the result.

    Args:
      json_file_reader: A file reader of a manysstubs4j raw data file.

    Yields:
      A dictionary with 'split', 'token' and 'label' as keys. The value of the
      'split' field is the split (train/valid/test) that the data belongs to.
      The value of the 'token' field tokens of the code snippet. The value of
      the 'label' split is the bug type of the raw data.
    """
    for json_data in json.load(json_file_reader):
      source_tokens, target_tokens = self._patch_to_source_and_target_tokens(
          json_data['fixPatch'])
      # Disregard empty code token list, it means that we failed to parse
      # the code snippet.
      if not source_tokens:
        continue
      # For each patch, we get the code snippet before the change (have bug),
      # and the code snippet after the change (bug free).
      yield {'split': self.random_split_fn(), 'tokens': source_tokens,
             'label': json_data['bugType']}
      yield {'split': self.random_split_fn(), 'tokens': target_tokens,
             'label': 'NO_BUG'}

  def process(self, file_path):
    """Function to read each json file."""
    with open(file_path) as f:
      raw_data_dict_generator = self._raw_data_dict_generator(f)
      for raw_data_dict in raw_data_dict_generator:
        yield raw_data_dict