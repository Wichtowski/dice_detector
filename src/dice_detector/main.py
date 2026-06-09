import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="D&D Dice Detector"
    )
    parser.add_argument(
        "--mode",
        choices=["gui", "api", "annotate", "train", "test"],
        default="gui",
        help="Application mode (default: gui)",
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="Camera index to use",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="API server host",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="API server port",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    parser.add_argument(
        "--images-dir",
        type=str,
        help="Directory containing images for annotation",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Output directory for annotations",
    )
    parser.add_argument(
        "--skip-capture",
        action="store_true",
        help="Skip camera capture and annotate existing images only",
    )
    parser.add_argument(
        "--model",
        type=str,
        help="Path to trained dice YOLO model (.pt)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Inference device: rocm/amd, cuda, mps, or cpu (default: auto)",
    )

    args = parser.parse_args()

    if args.mode == "gui":
        return run_gui(args.camera, args.model, args.device)
    elif args.mode == "api":
        return run_api(args.host, args.port, args.reload)
    elif args.mode == "annotate":
        return run_annotator(args)
    elif args.mode == "train":
        return run_training()
    elif args.mode == "test":
        return run_test(args)

    return 0


def run_gui(
    camera_index: int = 0,
    model_path: str | None = None,
    device: str | None = None,
) -> int:
    import os

    from dice_detector.ui import MainWindow

    if device:
        os.environ["DICE_DETECTOR_VISION__DEVICE"] = device

    app = MainWindow(initial_camera_index=camera_index, model_path=model_path)
    app.run()
    return 0


def run_api(host: str, port: int, reload: bool) -> int:
    import uvicorn

    print(f"Starting Dice Detector API at http://{host}:{port}")
    print(f"WebSocket available at ws://{host}:{port}/ws")
    print("Press Ctrl+C to stop")

    uvicorn.run(
        "dice_detector.api:app",
        host=host,
        port=port,
        reload=reload,
    )
    return 0


def run_annotator(args) -> int:
    from dice_detector.training import AnnotationTool
    from dice_detector.training.annotator_gui import run_session_gui

    if not args.images_dir:
        print("Error: --images-dir is required for annotation mode")
        return 1

    output_dir = args.output_dir or "data/annotations"
    tool = AnnotationTool(args.images_dir, output_dir)
    run_session_gui(tool, camera_index=args.camera, skip_capture=args.skip_capture)
    return 0


def run_training() -> int:
    from dice_detector.training import DatasetManager

    print("Training mode")
    print("=" * 50)

    dataset = DatasetManager()
    stats = dataset.get_statistics()

    print(f"Total images: {stats['total_images']}")
    print(f"Total annotations: {stats['total_annotations']}")
    print(f"By class: {stats['by_class']}")
    print(f"By split: {stats['by_split']}")

    if stats["total_images"] < 100:
        print("\nWarning: Dataset is small. Consider adding more samples.")
        print("Use annotation mode to add more labeled images.")
        return 0

    print("\nExporting dataset for YOLO training...")
    dataset.export_yolo_format("data/yolo_export")
    print("Dataset exported to data/yolo_export/")

    print("\nTo train the model, run:")
    print("  yolo detect train data=data/yolo_export/data.yaml model=yolo11n.pt epochs=150")
    return 0


def run_test(args) -> int:
    import cv2

    from dice_detector.camera import CameraCapture
    from dice_detector.models import CalibrationSettings
    from dice_detector.vision import VisionPipeline

    print("Running detection test...")
    print("Press 'q' to quit, 'd' to detect, 's' to save sample")

    from dice_detector.models import VisionConfig

    settings = CalibrationSettings(camera_index=args.camera)
    camera = CameraCapture(settings)
    pipeline = VisionPipeline(
        settings,
        model_path=args.model,
        vision_config=VisionConfig(device=args.device),
    )

    if not camera.start():
        print("Failed to start camera")
        return 1

    pipeline.initialize()
    cv2.namedWindow("Dice Detection Test")
    detected_dice = []

    while True:
        frame = camera.get_frame()
        if frame is None:
            continue

        if detected_dice:
            frame = pipeline.draw_results(frame, detected_dice)

        cv2.imshow("Dice Detection Test", frame)
        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            break
        elif key == ord("d"):
            detected_dice = pipeline.process_frame(frame)
            print(f"\nDetected {len(detected_dice)} dice:")
            for die in detected_dice:
                print(
                    f"  {die.dice_type.value}: {die.value} "
                    f"(confidence: {die.confidence:.2f})"
                )
        elif key == ord("s") and detected_dice:
            for die in detected_dice:
                path = pipeline.save_sample(frame, die)
                print(f"Saved sample: {path}")

    camera.stop()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
