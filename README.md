# PLUR

PLUR (Programming-Language Understanding and Repair) is a collection of
source code datasets suitable for graph-based machine learning. We provide
scripts for downloading, processing, and loading the datasets. This is done
by offering a unified API and data structures for all datasets.


## Installation

```bash
SRC_DIR=${HOME}/src
mkdir -p ${SRC_DIR} && cd ${SRC_DIR}
# For Cubert.
git clone https://github.com/google-research/google-research --depth=1
export PYTHONPATH=${PYTHONPATH}:${SRC_DIR}/google-research
git clone https://github.com/google-research/plur && cd plur
python -m pip install -r requirements.txt
python setup.py install
```

## Usage

### Basic usage

#### Data generation (step 1)

Data generation is done by calling `plur.plur_data_generation.create_dataset()`.
The data generation runs in two stages:

1. Convert raw data to `plur.utils.GraphToOutputExample`.
2. Convert `plur.utils.GraphToOutputExample` to `TFExample`.

Stage 1 is unique for each dataset, but stage 2 is the same for almost all datasets.

```python
from plur.plur_data_generation import create_dataset

dataset_name = 'code2seq_dataset'
dataset_stage_1_directory = '/tmp/code2seq_dataset/stage_1'
stage_1_kwargs = dict()
dataset_stage_2_directory = '/tmp/code2seq_dataset/stage_2'
stage_2_kwargs = dict()
create_dataset(dataset_name, dataset_stage_1_directory, dataset_stage_2_directory, stage_1_kwargs, stage_2_kwargs)
```

`plur_data_generation.py` also provides a command line interface, but it offers less flexibility.

```bash
python3 plur_data_generation.py --stage_1_dir=/tmp/code2seq_dataset/stage_1 --stage_2_dir=/tmp/code2seq_dataset/stage_2
```

#### Data loader (step 2)

After the data is generated, you can use `PlurDataLoader` to load the data. The data loader loads `TFExample`s but returns them as numpy arrays.

```python
from plur.plur_data_loader import PlurDataLoader
from plur.util import constants

dataset_stage_2_directory = '/tmp/code2seq_dataset/stage_2'
split = constants.TRAIN_SPLIT_NAME
batch_size = 32
repeat_count = -1
drop_remainder = True
train_data_generator = PlurDataLoader(dataset_stage_2_directory, split, batch_size, repeat_count, drop_remainder)

for batch_data in train_data_generator:
  # your training loop...
```

#### Training (step 3)

This is the part where you use your own model to train on the PLUR data.

The models and the training code from the PLUR paper are not yet part of the
current release. We plan to release it in the near future.

#### Evaluating (step 4)

Once the training is finished, you can generate the predictions on the test data and use `plur_evaluator.py` to evaluate the performance. `plur_evaluator.py` works in offline mode, meaning that it expects a file containing the ground truths, and a file containing the predictions.

```bash
python3 plur_evaluator.py --dataset_name=code2seq_dataset --target_file=/tmp/code2seq_dataset/targets.txt --prediction_file=/tmp/code2seq_dataset/predictions.txt
```

### Transforming and filtering data

If there is something fundamental you want to change in the dataset, you should apply them in stage 1 of data generation, otherwise apply them in stage 2. The idea is that stage 1 should only be run once per dataset (to create the `plur.utils.GraphToOutputExample`), and stage 2 should be run each time you want to train on different data (to create the TFRecords).

All transformation and filtering functions are applied on `plur.utils.GraphToOutputExample`, see `plur.utils.GraphToOutputExample` for more information.

E.g. a transformation that can be run in stage 1 is that your model expects that graphs in the dataset have no loop, and you write your transformation function to remove loops. This will ensure that stage 2 will read data where the graph has no loops.

E.g. of filters that can be run in stage 2 is that you want to check your model performance on different graph sizes in terms of number of nodes. You write your own filter function to filter graphs with a large number of nodes.

```python
from plur.plur_data_generation import create_dataset

dataset_name = 'code2seq_dataset'
dataset_stage_1_directory = '/tmp/code2seq_dataset/stage_1'
stage_1_kwargs = dict()
dataset_stage_2_directory = '/tmp/code2seq_dataset/stage_2'
def _filter_graph_size(graph_to_output_example, graph_size=1024):
  return len(graph_to_output_example.get_nodes()) <= graph_size
stage_2_kwargs = dict(
    train_filter_funcs=(_filter_graph_size,),
    validation_filter_funcs=(_filter_graph_size,)
)
create_dataset(dataset_name, dataset_stage_1_directory, dataset_stage_2_directory, stage_1_kwargs, stage_2_kwargs)
```

### Advanced usage

`plur.plur_data_generation.create_dataset()` is just a thin wrapper around `plur.stage_1.plur_dataset` and `plur.stage_2.graph_to_output_example_to_tfexample`.

```python
from plur.plur_data_generation import create_dataset

dataset_name = 'code2seq_dataset'
dataset_stage_1_directory = '/tmp/code2seq_dataset/stage_1'
stage_1_kwargs = dict()
dataset_stage_2_directory = '/tmp/code2seq_dataset/stage_2'
stage_2_kwargs = dict()
create_dataset(dataset_name, dataset_stage_1_directory, dataset_stage_2_directory, stage_1_kwargs, stage_2_kwargs)
```

is equivalent to

```python
from plur.stage_1.code2seq_dataset import Code2seqDataset
from plur.stage_2.graph_to_output_example_to_tfexample import GraphToOutputExampleToTfexample

dataset_name = 'code2seq_dataset'
dataset_stage_1_directory = '/tmp/code2seq_dataset/stage_1'
dataset_stage_2_directory = '/tmp/code2seq_dataset/stage_2'
dataset = Code2seqDataset(dataset_stage_1_directory)
dataest.stage_1_mkdirs()
dataset.download_dataset()
dataset.run_pipeline()

dataset = GraphToOutputExampleToTfexample(dataset_stage_1_directory, dataset_stage_2_directory, dataset_name)
dataset.stage_2_mkdirs()
dataset.run_pipeline()
```

You can check out `plur.stage_1.code2seq_dataset` for arguments relevant for code2seq dataset. For example code2seq dataset provides `java-small`, `java-med` and `java-large` datasets. Therefore you can create a `java-large` dataset in this way.

```python
from plur.stage_1.code2seq_dataset import Code2seqDataset

dataset_name = 'code2seq_dataset'
dataset_stage_1_directory = '/tmp/code2seq_dataset/stage_1'

dataset = Code2seqDataset(dataset_stage_1_directory, dataset_size='large')
dataest.stage_1_mkdirs()
dataset.download_dataset()
dataset.run_pipeline()
```

## Adding a new dataset

All datasets should inherit `plur.stage_1.plur_dataset.PlurDataset`, and placed under `plur/stage_1/`, which requires you to implement:

* `download_dataset()`: Code to download the dataset, we provide `download_dataset_using_git()` to download from git and `download_dataset_using_requests()` to download from a URL, which also works with a Google Drive URL. In `download_dataset_using_git()` we download the dataset from a specific commit id. In `download_dataset_using_requests()` we check the sha1sum for the downloaded files. This is to ensure that the same version of PLUR downloads the same raw data.
* `get_all_raw_data_paths()`: It should return a list of paths, where each path is a file containing the raw data in the datasets.
* `raw_data_paths_to_raw_data_do_fn()`: It should return a `beam.DoFn` class that overrides `process()`. The `process()` should tell beam how to open the files returned by `get_all_raw_data_paths()`. It is also here we define if the data belongs to any split (train/validation/test).
* `raw_data_to_graph_to_output_example()`: This function transforms raw data from `raw_data_paths_to_raw_data_do_fn()` to `GraphToOutputExample`.

Then add/change the following lines in `plur/plur_data_generation.py`:

```python
from plur.stage_1.foo_dataset import FooDataset

flags.DEFINE_enum('dataset_name', 'dummy_dataset',
                  ['code2seq_dataset', 'dummy_dataset',
                   'funcom_dataset', 'great_var_misuse_dataset',
                   'hoppity_single_ast_diff_dataset',
                   'manysstubs4j_dataset', 'foo_dataset'],
                  'Name of the dataset to generate data.')


def get_dataset_class(dataset_name):
  """Get the dataset class based on dataset_name."""
  if dataset_name == 'code2seq_dataset':
    return Code2SeqDataset
  elif dataset_name == 'dummy_dataset':
    return DummyDataset
  elif dataset_name == 'funcom_dataset':
    return FuncomDataset
  elif dataset_name == 'great_var_misuse_dataset':
    return GreatVarMisuseDataset
  elif dataset_name == 'hoppity_single_ast_diff_dataset':
    return HoppitySingleAstDiffDataset
  elif dataset_name == 'manysstubs4j_dataset':
    return ManySStuBs4JDataset
  elif dataset_name == 'foo_dataset':
    return FooDataset
  else:
    raise ValueError('{} is not supported.'.format(dataset_name))
```

## Evaluation details

The details of how evaluation is performed are in `plur/eval/README.md`.

## License

Licensed under the Apache 2.0 License.

## Disclaimer

This is not an officially supported Google product.

## Citation

Please cite the PLUR paper, Chen et al. https://proceedings.neurips.cc//paper/2021/hash/c2937f3a1b3a177d2408574da0245a19-Abstract.html