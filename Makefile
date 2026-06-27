.PHONY: help install dev \
       run api \
       synthetic synthetic-preview check-gaps \
       annotator-api annotator-ui \
       lint typecheck test format \
       clean clean-synthetic kaggle-dataset

# Config
BLEND_FILE     ?= blender/dices.blend
SYNTH_CONFIG   ?= synthetic/blender/configs/default_blender_generation.json
SYNTH_OUTPUT   ?= blender/data_synthetic
NUM_IMAGES     ?= 100
WORKERS        ?= 4
SEED           ?=
HOST           ?= 127.0.0.1
PORT           ?= 8765
IMAGES_DIR     ?= data/web/images
ANNOT_DIR      ?= data/web/annotations

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:
	uv sync

run: api

api:
	uv run uvicorn dice_detector.api:app --host $(HOST) --port $(PORT)

synthetic: ## Generate synthetic dataset with Blender
	uv run python synthetic/generate.py \
		--num-images $(NUM_IMAGES) --config $(SYNTH_CONFIG) --output $(SYNTH_OUTPUT) \
		--blend-file $(BLEND_FILE) $(if $(SEED),--seed $(SEED),) \
		$(if $(filter-out 1,$(WORKERS)),--workers $(WORKERS),) \
		$(if $(ADD_ANNOTATED_IMAGES),--add-annotated-images,)

synthetic_preview: ## Generate 1 image for preview
	uv run python synthetic/generate.py \
		--num-images 1 --config $(SYNTH_CONFIG) --output $(SYNTH_OUTPUT) \
		--blend-file $(BLEND_FILE) $(if $(SEED),--seed $(SEED),)

synthetic_gui: ## Generate with Blender GUI (for debugging)
	uv run python synthetic/generate.py \
		--num-images 1 --config $(SYNTH_CONFIG) --output $(SYNTH_OUTPUT) \
		--blend-file $(BLEND_FILE) --no-background

check_gaps: ## Check for gaps in synthetic renders
	uv run python synthetic/check_gaps.py --output $(SYNTH_OUTPUT)

convert_annotations: ## Convert JSON annotations to YOLO .txt labels
	uv run python synthetic/convert_annotations.py --data-dir $(SYNTH_OUTPUT)

annotator-api:
	@if v4l2-ctl --list-devices 2>/dev/null | grep -q "Pixel"; then \
		echo "Pixel camera already active"; \
	elif [ -e /dev/video0 ]; then \
		scrcpy --video-source=camera --camera-id=0 --camera-size=1920x1080 --v4l2-sink=/dev/video0 --no-playback & \
		echo "Started Pixel camera stream"; \
		sleep 2; \
	else \
		echo "Warning: /dev/video0 not found. Run: sudo modprobe v4l2loopback devices=1 video_nr=0 card_label=Pixel_Webcam"; \
	fi
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

clean_synthetic: ## Remove all generated synthetic data
	find $(SYNTH_OUTPUT)/images -type f ! -name '.gitkeep' -delete 2>/dev/null || true
	find $(SYNTH_OUTPUT)/images_annotated -type f ! -name '.gitkeep' -delete 2>/dev/null || true
	find $(SYNTH_OUTPUT)/annotations -type f ! -name '.gitkeep' -delete 2>/dev/null || true
	find $(SYNTH_OUTPUT)/metadata -type f ! -name '.gitkeep' -delete 2>/dev/null || true
	find $(SYNTH_OUTPUT)/labels -type f ! -name '.gitkeep' -delete 2>/dev/null || true
	find $(SYNTH_OUTPUT)/logs -type f ! -name '.gitkeep' -delete 2>/dev/null || true
	@echo "Cleaned synthetic data from $(SYNTH_OUTPUT)"
