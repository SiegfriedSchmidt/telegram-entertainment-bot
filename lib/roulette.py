import cv2
import numpy as np

from lib.init import tmp_folder_path
from lib.opencv_custom_writer import OpencvCustomWriter
from lib.utils.cv2_utils import cv2_paste_with_alpha

# Real European roulette order (clockwise, starting from 0)
ROULETTE_NUMBERS = [
    0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11,
    30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18,
    29, 7, 28, 12, 35, 3, 26
]

WIDTH = 600
HEIGHT = 600
RADIUS = 250
INNER_RADIUS = int(RADIUS * 0.75)
TEXT_RADIUS = INNER_RADIUS + (RADIUS - INNER_RADIUS) // 2
GOLDEN_RING_RADIUS = 4
BALL_RADIUS = 10
WHITE_BORDER_WIDTH = 3
CENTER = (RADIUS, RADIUS)
NUM_SECTORS = len(ROULETTE_NUMBERS)
SECTOR_ANGLE = 360.0 / NUM_SECTORS

FONT = cv2.FONT_HERSHEY_DUPLEX
FONT_SCALE = 0.6
FONT_THICKNESS = 2
FONT_OUTLINE_THICKNESS = 4

RED = (0, 0, 255, 255)  # BGRA
BLACK = (0, 0, 0, 255)
GREEN = (0, 255, 0, 255)
WHITE = (255, 255, 255, 255)
GOLDEN = (0, 215, 255, 255)
TEXT_COLOR = (255, 255, 255, 255)
OUTLINE_COLOR = (0, 0, 0, 255)


def put_rotated_text(image, text, position, angle, color=(255, 255, 255)):
    """
    Put rotated text on an image
    """

    # Create a blank image for the text
    text_image = np.zeros_like(image)

    # Get text size
    text_size, _ = cv2.getTextSize(text, FONT, FONT_SCALE, FONT_THICKNESS)
    text_width, text_height = text_size

    # Calculate position to put text (centered on given position)
    x = position[0] - text_width // 2
    y = position[1]

    # Put text on blank image
    # cv2.putText(text_image, text, (x, y), font, font_scale, OUTLINE_COLOR, outline_thickness, cv2.LINE_AA)
    cv2.putText(text_image, text, (x, y), FONT, FONT_SCALE, color, FONT_THICKNESS)

    # Get rotation matrix
    center = position
    rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)

    # Rotate the text image
    rotated_text = cv2.warpAffine(text_image, rotation_matrix, (image.shape[1], image.shape[0]))

    # Combine with original image
    mask = rotated_text > 0
    image[mask] = rotated_text[mask]

    return image


def draw_white_border(wheel: np.ndarray, angle: float):
    x1 = int(CENTER[0] + RADIUS * np.cos(np.radians(angle)))
    y1 = int(CENTER[1] + RADIUS * np.sin(np.radians(angle)))
    cv2.line(wheel, CENTER, (x1, y1), WHITE, WHITE_BORDER_WIDTH)


def create_wheel(angle: float) -> np.ndarray:
    # Create transparent wheel
    wheel = np.full((RADIUS * 2, RADIUS * 2, 4), (0, 0, 0, 0), dtype=np.uint8)

    # Outer dark background circle
    cv2.circle(wheel, CENTER, RADIUS, (40, 40, 80, 255), -1)

    # Draw colored sectors
    for i in range(NUM_SECTORS):
        start_angle = i * SECTOR_ANGLE + angle
        end_angle = start_angle + SECTOR_ANGLE

        if ROULETTE_NUMBERS[i] == 0:
            color = GREEN
        else:
            color = RED if (i % 2 == 1) else BLACK

        cv2.ellipse(
            wheel, CENTER,
            (RADIUS, RADIUS),
            0,
            start_angle,
            end_angle,
            color,
            -1
        )

        # white borders
        draw_white_border(wheel, start_angle)

        # text
        number = ROULETTE_NUMBERS[i]
        mid_angle = (start_angle + end_angle) / 2

        rad = np.radians(mid_angle)
        x = int(CENTER[0] + TEXT_RADIUS * np.cos(rad))
        y = int(CENTER[1] + TEXT_RADIUS * np.sin(rad))

        put_rotated_text(wheel, str(number), (x, y), -(mid_angle + 90), TEXT_COLOR)

    # last white border
    draw_white_border(wheel, NUM_SECTORS * SECTOR_ANGLE + angle)

    # Inner circle
    cv2.circle(wheel, CENTER, INNER_RADIUS, (20, 20, 60, 255), -1)

    # Golden ring
    cv2.circle(wheel, CENTER, INNER_RADIUS + GOLDEN_RING_RADIUS, GOLDEN, GOLDEN_RING_RADIUS * 2)

    return wheel


def draw_ball(wheel: np.ndarray, angle: float) -> None:
    x = int(CENTER[0] + (INNER_RADIUS + GOLDEN_RING_RADIUS) * np.cos(np.radians(angle)))
    y = int(CENTER[1] + (INNER_RADIUS + GOLDEN_RING_RADIUS) * np.sin(np.radians(angle)))
    cv2.circle(wheel, (x, y), BALL_RADIUS, WHITE, -1)


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def generate_roulette_angles(
        winning_number: int,
        total_seconds: float,
        fps: int,
        wheel_extra_spins: int = 12,  # tune these if you want more/less drama
        ball_extra_spins: int = 18
) -> list[tuple[float, float]]:
    """
    Returns list of (wheel_angle, ball_angle) for every frame.
    Wheel stops earlier than ball.
    """
    total_frames = int(total_seconds * fps)
    frames = []

    # Find index of winning number
    winning_idx = ROULETTE_NUMBERS.index(winning_number)

    # Final wheel angle so the winning sector center is exactly under the fixed pointer (top)
    # Negative because wheel spins clockwise
    final_wheel_angle = -(winning_idx * SECTOR_ANGLE + SECTOR_ANGLE / 2.0)

    # Ball always stops at the top (under the pointer) — this makes it look like it "falls in"
    final_ball_angle = 0.0

    # Start angles = final + many extra full spins
    start_wheel_angle = final_wheel_angle - wheel_extra_spins * 360.0
    start_ball_angle = final_ball_angle + ball_extra_spins * 360.0  # opposite direction

    # Wheel stops earlier than total time
    wheel_stop_fraction = np.random.uniform(0.85, 0.95)

    for i in range(total_frames):
        t = i / (total_frames - 1)  # 0.0 → 1.0

        # === WHEEL (stops earlier) ===
        if t < wheel_stop_fraction:
            wheel_t = t / wheel_stop_fraction
        else:
            wheel_t = 1.0
        wheel_eased = ease_out_cubic(wheel_t)
        wheel_angle = start_wheel_angle + (final_wheel_angle - start_wheel_angle) * wheel_eased

        # === BALL (spins a bit longer) ===
        ball_eased = ease_out_cubic(t)  # full duration
        ball_angle = start_ball_angle + (final_ball_angle - start_ball_angle) * ball_eased

        frames.append((wheel_angle, ball_angle))

    return frames


def render_roulette() -> tuple[str, float, int]:
    background = np.full((HEIGHT, WIDTH, 3), (172, 146, 140), dtype=np.uint8)

    fps = 24
    total_seconds = np.random.uniform(10.0, 15.0)
    filename = tmp_folder_path / f'roulette_{np.random.randint(0, 1 << 31)}.mp4'

    winning_number = np.random.choice(ROULETTE_NUMBERS)
    angles = generate_roulette_angles(winning_number, total_seconds, fps)
    print(len(angles))

    with OpencvCustomWriter(fps, WIDTH, HEIGHT, filename) as writer:
        for wheel_angle, ball_angle in angles:
            img = background.copy()
            wheel = create_wheel(wheel_angle)
            draw_ball(wheel, ball_angle)
            cv2_paste_with_alpha(img, wheel, (WIDTH // 2 - RADIUS, HEIGHT // 2 - RADIUS))
            writer.write(img)

    return filename, total_seconds, winning_number


if __name__ == '__main__':
    render_roulette()
