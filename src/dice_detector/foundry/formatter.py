from dice_detector.models import RollResult


class MessageFormatter:
    def format_roll(self, result: RollResult) -> str:
        return result.to_markdown()
