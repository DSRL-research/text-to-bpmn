#!/bin/bash
# The winner and the BERT baseline over the same five folds, one after the other.
# Each fold starts from the pretrained checkpoint: a model already fine-tuned on
# this corpus has seen every fold's held-out part.
cd "$(dirname "$0")/../.." || exit 1
echo "=== gliner-small cv started $(date -Is)"
timeout 14400 $HOME/.venvs/gliner-env/bin/python -m text2bpmn.cross_validate --model gliner \
    --base urchade/gliner_small-v2.1 --name gliner-small --epochs 10 --threshold 0.9 \
    --out text2bpmn/baselines/cv > text2bpmn/baselines/cv_gliner.log 2>&1
echo "=== gliner-small cv exit $? at $(date -Is)"
echo "=== bert cv started $(date -Is)"
# USE_TF=0 keeps transformers from importing TensorFlow. This environment has
# tensorflow 2.19 with protobuf 6.33, where MessageFactory.GetPrototype no longer
# exists; the import raises, and TensorFlow's native layer then segfaults the
# process. Nothing about the comparison depends on TensorFlow being loaded.
USE_TF=0 TRANSFORMERS_NO_TF=1 timeout 14400 python3 -m text2bpmn.cross_validate --model bert \
    --base bert-base-cased --name bert-base --epochs 9 \
    --out text2bpmn/baselines/cv > text2bpmn/baselines/cv_bert.log 2>&1
echo "=== bert cv exit $? at $(date -Is)"
