# Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

import pytorch_lightning as pl
from omegaconf import DictConfig

from nemo.collections.nlp.models import TokenClassificationModel
from nemo.core.config import hydra_runner
from nemo.utils import logging
from nemo.utils.exp_manager import exp_manager


"""
This script shows how to perform evaluation and runs inference of a few examples.
The script runs two types of evaluation: 
    * model.test() - this eval will use the config setting for evaluation such as model.dataset.max_seq_length
    * model.evaluate_from_file():
        * disregards model.dataset.max_seq_length and evaluate all the tokens
        * creates confusion matrix
        * saves predictions and labels (if provided)

To run the script:

    python token_classification_evaluate.py \
    model.dataset.data_dir=<PATH_TO_DATA_DIR>  \
    pretrained_model=NERModel 

<PATH_TO_DATA_DIR> - a directory that contains test_ds.text_file and test_ds.labels_file (see the config)
pretrained_model   - pretrained TokenClassification model from list_available_models() or 
                     path to a .nemo file, for example: NERModel or model.nemo

More details on Token Classification model could be found in
tutorials/nlp/Token_Classification_Named_Entity_Recognition.ipynb

For more ways of restoring a pre-trained model, see tutorials/00_NeMo_Primer.ipynb
"""


@hydra_runner(config_path="../conf", config_name="token_classification_config")
def main(cfg: DictConfig) -> None:
    logging.info(
        'During evaluation/testing, it is currently advisable to construct a new Trainer with single GPU and \
            no DDP to obtain accurate results'
    )

    if not hasattr(cfg.model, 'test_ds'):
        raise ValueError(f'model.test_ds was not found in the config, skipping evaluation')
    else:
        gpu = 1 if cfg.trainer.gpus != 0 else 0

    trainer = pl.Trainer(
        gpus=gpu,
        precision=cfg.trainer.precision,
        amp_level=cfg.trainer.amp_level,
        logger=False,
        checkpoint_callback=False,
    )
    exp_dir = exp_manager(trainer, cfg.exp_manager)

    if not cfg.pretrained_model:
        raise ValueError(
            'To run evaluation and inference script a pre-trained model or .nemo file must be provided.'
            'For example: "pretrained_model"="NERModel" or "pretrained_model"="my_ner_model.nemo"'
        )

    if os.path.exists(cfg.pretrained_model):
        model = TokenClassificationModel.restore_from(cfg.pretrained_model)
    elif cfg.pretrained_model in TokenClassificationModel.get_available_model_names():
        model = TokenClassificationModel.from_pretrained(cfg.pretrained_model)
    else:
        raise ValueError(
            f'Provide path to the pre-trained checkpoint or choose from {TokenClassificationModel.list_available_models()}'
        )

    data_dir = cfg.model.dataset.get('data_dir', None)
    if not data_dir:
        raise ValueError(
            'Specify a valid dataset directory that contains test_ds.text_file and test_ds.labels_file \
            with "model.dataset.data_dir" argument'
        )

    if not os.path.exists(data_dir):
        raise ValueError(f'{data_dir} is not found at')

    model.update_data_dir(data_dir=data_dir)
    model._cfg.dataset.use_cache = False

    if not hasattr(cfg.model, 'test_ds'):
        raise ValueError(f'model.test_ds was not found in the config, skipping evaluation')
    else:
        if model.prepare_test(trainer):
            model.setup_test_data()
            trainer.test(model)
        else:
            raise ValueError('Terminating evaluation')

    model.evaluate_from_file(
        text_file=os.path.join(data_dir, cfg.model.test_ds.text_file),
        labels_file=os.path.join(data_dir, cfg.model.test_ds.labels_file),
        output_dir=exp_dir,
        add_confusion_matrix=True,
        normalize_confusion_matrix=True,
    )

    # run an inference on a few examples
    queries = ['we bought four shirts from the nvidia gear store in santa clara.', 'Nvidia is a company.']
    results = model.add_predictions(queries, output_file='predictions.txt')

    for query, result in zip(queries, results):
        logging.info(f'Query : {query}')
        logging.info(f'Result: {result.strip()}\n')

    logging.info(f'Results are saved at {exp_dir}')


if __name__ == '__main__':
    main()
