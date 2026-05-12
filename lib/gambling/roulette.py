import cv2
import numpy as np
from lib.init import tmp_folder_path, roulette_assets_folder_path, blackjack_assets_folder_path
from lib.utils.cv2_utils import cv2_paste_with_alpha, OpencvCustomWriter

# European roulette order (clockwise, starting from 0)
ROULETTE_NUMBERS = [
    0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11,
    30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18,
    29, 7, 28, 12, 35, 3, 26
]

WIDTH = 680
HEIGHT = 900
BALL_RADIUS = 10
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


def draw_white_border(wheel: np.ndarray, radius: int, center: tuple[int, int], white_border_width: int, angle: float):
    x1 = int(center[0] + radius * np.cos(np.radians(angle)))
    y1 = int(center[1] + radius * np.sin(np.radians(angle)))
    cv2.line(wheel, center, (x1, y1), WHITE, white_border_width)


def create_wheel(radius: int, angle: float) -> np.ndarray:
    inner_radius = int(radius * 0.75)
    text_radius = inner_radius + (radius - inner_radius) // 2
    golden_ring_radius = 4
    white_border_width = 3
    center = (radius, radius)

    # Create transparent wheel
    wheel = np.full((radius * 2, radius * 2, 4), (0, 0, 0, 0), dtype=np.uint8)

    # Outer dark background circle
    cv2.circle(wheel, center, radius, (40, 40, 80, 255), -1)

    # Draw colored sectors
    for i in range(NUM_SECTORS):
        start_angle = i * SECTOR_ANGLE + angle
        end_angle = start_angle + SECTOR_ANGLE

        if ROULETTE_NUMBERS[i] == 0:
            color = GREEN
        else:
            color = RED if (i % 2 == 1) else BLACK

        cv2.ellipse(
            wheel,
            center,
            (radius, radius),
            0,
            start_angle,
            end_angle,
            color,
            -1
        )

        # white borders
        draw_white_border(wheel, radius, center, white_border_width, start_angle)

        # text
        number = ROULETTE_NUMBERS[i]
        mid_angle = (start_angle + end_angle) / 2

        rad = np.radians(mid_angle)
        x = int(center[0] + text_radius * np.cos(rad))
        y = int(center[1] + text_radius * np.sin(rad))

        put_rotated_text(wheel, str(number), (x, y), -(mid_angle + 90), TEXT_COLOR)

    # last white border
    draw_white_border(wheel, radius, center, white_border_width, NUM_SECTORS * SECTOR_ANGLE + angle)

    # Inner circle
    cv2.circle(wheel, center, inner_radius, (20, 20, 60, 255), -1)

    # Golden ring
    cv2.circle(wheel, center, inner_radius + golden_ring_radius, GOLDEN, golden_ring_radius * 2)

    return wheel


def draw_ball(wheel: np.ndarray, center: tuple[int, int], radius: int, angle: float) -> None:
    x = int(center[0] + radius * np.cos(np.radians(angle)))
    y = int(center[1] + radius * np.sin(np.radians(angle)))
    cv2.circle(wheel, (x, y), BALL_RADIUS, WHITE, -1)


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def generate_roulette_angles(
        winning_number: int,
        total_seconds: float,
        fps: int,
        wheel_extra_spins: int | None = None,
        ball_extra_spins: int | None = None,
) -> list[tuple[float, float]]:
    if wheel_extra_spins is None:
        wheel_extra_spins = np.random.randint(6, 18)
    if ball_extra_spins is None:
        ball_extra_spins = np.random.randint(6, 18)

    total_frames = int(total_seconds * fps)
    frames = []

    # Find index of winning number
    winning_idx = ROULETTE_NUMBERS.index(winning_number)
    random_idx = np.random.randint(len(ROULETTE_NUMBERS) / 2, len(ROULETTE_NUMBERS))

    final_ball_angle = random_idx * SECTOR_ANGLE
    final_wheel_angle = -((winning_idx - random_idx) * SECTOR_ANGLE + SECTOR_ANGLE / 2.0)

    # Start angles = final + many extra full spins
    start_wheel_angle = final_wheel_angle - wheel_extra_spins * 360.0
    start_ball_angle = final_ball_angle + ball_extra_spins * 360.0  # opposite direction

    # Wheel stops earlier than total time
    wheel_stop_fraction = np.random.uniform(0.85, 0.95)

    for i in range(total_frames):
        t = i / (total_frames - 1)  # 0.0 → 1.0

        # === WHEEL (stops earlier) ===
        wheel_eased = ease_out_cubic(min(t, wheel_stop_fraction) / wheel_stop_fraction)
        wheel_angle = start_wheel_angle + (final_wheel_angle - start_wheel_angle) * wheel_eased

        # === BALL (spins a bit longer) ===
        ball_eased = ease_out_cubic(t)  # full duration
        ball_angle = start_ball_angle + (final_ball_angle - start_ball_angle) * ball_eased

        frames.append((wheel_angle, ball_angle))

    return frames


# background = np.full((HEIGHT, WIDTH, 3), (172, 146, 140), dtype=np.uint8)
background = cv2.imread(blackjack_assets_folder_path / "background.png", cv2.IMREAD_UNCHANGED)
background = background[0:HEIGHT, 0:WIDTH]

wheel_original = create_wheel(250, 0)
# wheel_original = cv2.imread(roulette_assets_folder_path / 'wheel.png', cv2.IMREAD_UNCHANGED)
wheel_size = wheel_original.shape[:2]
wheel_center = int(wheel_size[1] / 2), int(wheel_size[0] / 2)
wheel_pad_x = (WIDTH - wheel_size[1]) // 2
wheel_pad_y = 20

table = cv2.imread(roulette_assets_folder_path / 'table.png', cv2.IMREAD_UNCHANGED)
table_size = table.shape[:2]
table_pad_x = (WIDTH - table_size[1]) // 2
table_pad_y = wheel_size[0] + wheel_pad_y + (HEIGHT - table_size[0] - wheel_pad_y - wheel_size[0]) // 2

cv2_paste_with_alpha(background, table, (table_pad_x, table_pad_y))


def render_roulette() -> tuple[str, float, int]:
    fps = 30
    total_seconds = np.random.uniform(8.0, 12.0)
    filename = tmp_folder_path / f'roulette_{np.random.randint(0, 1 << 31)}.mp4'

    winning_number = np.random.choice(ROULETTE_NUMBERS)
    angles = generate_roulette_angles(winning_number, total_seconds, fps)

    with OpencvCustomWriter(fps, WIDTH, HEIGHT, filename) as writer:
        for wheel_angle, ball_angle in angles:
            img = background.copy()
            rotation_matrix = cv2.getRotationMatrix2D(wheel_center, -wheel_angle, 1)
            wheel = cv2.warpAffine(wheel_original, rotation_matrix, wheel_size, cv2.INTER_LINEAR)
            draw_ball(wheel, wheel_center, int(wheel_center[0] * 0.75) + 2, ball_angle)
            cv2_paste_with_alpha(img, wheel, (wheel_pad_x, wheel_pad_y))
            # cv2.imshow("wheel", img)
            # cv2.waitKey(1000 // fps)
            writer.write(img)

    return filename, total_seconds, winning_number


if __name__ == '__main__':
    _, seconds, win = render_roulette()
    print(seconds, win)
