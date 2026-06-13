.PHONY: help install install-amd install-nvidia dev \
       run gui api test-detect annotate \
       train train-detect train-recog train-all evaluate export \
       synthetic synthetic-preview check-gaps \
       annotator-api annotator-ui \
       lint typecheck test format \
       clean clean-synthetic kaggle-dataset

# Config
BLEND_FILE     ?= blender/dices.blend
SYNTH_CONFIG   ?= synthetic/blender/configs/default_blender_generation.json
SYNTH_OUTPUT   ?= data/generated/blender
NUM_IMAGES     ?= 100
WORKERS        ?= 4
SEED           ?=
CAMERA         ?= 0
MODEL          ?=
HOST           ?= 127.0.0.1
PORT           ?= 8765
EPOCHS         ?= 100
BATCH          ?= 16
IMGSZ          ?= 640
DATASET        ?= data/dataset
IMAGES_DIR     ?= data/images
ANNOT_DIR      ?= data/annotations

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:
	uv sync

install-amd:
	uv sync --extra amd

install-nvidia:
	uv sync --extra nvidia

run: gui

gui:
	uv run dice-detector --mode gui $(if $(MODEL),--model $(MODEL),) --camera $(CAMERA)

api:
	uv run dice-detector --mode api --host $(HOST) --port $(PORT)

test-detect:
	uv run dice-detector --mode test --camera $(CAMERA) $(if $(MODEL),--model $(MODEL),)

annotate:
	uv run dice-detector --mode annotate --images-dir $(IMAGES_DIR) --output-dir $(ANNOT_DIR)

train:
	uv run python -m dice_detector.training.train \
		--action train --data $(DATASET) --epochs $(EPOCHS) --batch $(BATCH) --imgsz $(IMGSZ) \
		$(if $(MODEL),--model $(MODEL),)

train-detect: ## Train detection
	uv run python -m dice_detector.training.multi_output_trainer \
		--action train-detection --dataset $(DATASET) --epochs $(EPOCHS) --batch $(BATCH)

train-recog: ## Train recognition
	uv run python -m dice_detector.training.multi_output_trainer \
		--action train-recognition --dataset $(DATASET) --epochs $(EPOCHS) --batch $(BATCH)

train-all: ## Train both
	uv run python -m dice_detector.training.multi_output_trainer \
		--action train-all --dataset $(DATASET) --epochs $(EPOCHS) --batch $(BATCH)

evaluate: ## Evaluate trained model
	uv run python -m dice_detector.training.train --action evaluate --data $(DATASET) \
		$(if $(MODEL),--model $(MODEL),)

export: ## Export model to ONNX/TensorRT
	uv run python -m dice_detector.training.train --action export \
		$(if $(MODEL),--model $(MODEL),)

prepare-dataset:
	uv run python -m dice_detector.training.train --action prepare --data $(DATASET)

synthetic: ## Generate synthetic dataset with Blender
	uv run python synthetic/generate.py \
		--num-images $(NUM_IMAGES) --config $(SYNTH_CONFIG) --output $(SYNTH_OUTPUT) \
		--blend-file $(BLEND_FILE) $(if $(SEED),--seed $(SEED),) \
		$(if $(filter-out 1,$(WORKERS)),--workers $(WORKERS),) \
		$(if $(ADD_ANNOTATED_IMAGES),--add-annotated-images,)

synthetic-preview: ## Generate 1 image for preview
	uv run python synthetic/generate.py \
		--num-images 1 --config $(SYNTH_CONFIG) --output $(SYNTH_OUTPUT) \
		--blend-file $(BLEND_FILE) $(if $(SEED),--seed $(SEED),)

synthetic-gui: ## Generate with Blender GUI (for debugging)
	uv run python synthetic/generate.py \
		--num-images 1 --config $(SYNTH_CONFIG) --output $(SYNTH_OUTPUT) \
		--blend-file $(BLEND_FILE) --no-background

check-gaps: ## Check for gaps in synthetic renders
	uv run python synthetic/check_gaps.py --output $(SYNTH_OUTPUT)

annotator-api:
	uv run python -m dice_detector.training.annotator_api \
		--images $(IMAGES_DIR) --output $(ANNOT_DIR) --host $(HOST) --port $(PORT)

annotator-ui:
	cd annotator-ui && npm run dev

lint:
	uv run ruff check src/ tests/ synthetic/

format:
	uv run ruff format src/ tests/ synthetic/

typecheck:
	uv run mypy src/

test:
	uv run pytest

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .mypy_cache .pytest_cache .ruff_cache dist build *.egg-info

clean-synthetic: ## Remove all generated synthetic data
	find $(SYNTH_OUTPUT)/images -type f ! -name '.gitkeep' -delete 2>/dev/null || true
	find $(SYNTH_OUTPUT)/images_annotated -type f ! -name '.gitkeep' -delete 2>/dev/null || true
	find $(SYNTH_OUTPUT)/annotations -type f ! -name '.gitkeep' -delete 2>/dev/null || true
	find $(SYNTH_OUTPUT)/metadata -type f ! -name '.gitkeep' -delete 2>/dev/null || true
	find $(SYNTH_OUTPUT)/logs -type f ! -name '.gitkeep' -delete 2>/dev/null || true
	@echo "Cleaned synthetic data from $(SYNTH_OUTPUT)"
