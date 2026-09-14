import cv2
import numpy as np
from dataclasses import dataclass
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

# ----------------------------------------------------------------------------- what can be bet on
RED_NUMBERS = frozenset({1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36})
BLACK_NUMBERS = frozenset(range(1, 37)) - RED_NUMBERS
ODD_NUMBERS = frozenset(range(1, 37, 2))
EVEN_NUMBERS = frozenset(range(2, 37, 2))
LOW_NUMBERS = frozenset(range(1, 19))
HIGH_NUMBERS = frozenset(range(19, 37))

STRAIGHT_PAYOUT = 36  # 35:1
EVEN_MONEY_PAYOUT = 2  # 1:1
THIRD_PAYOUT = 3  # 2:1


@dataclass(frozen=True)
class Spot:
    """A place on the table: the numbers it covers, what a win pays, and where its chips go."""
    name: str
    numbers: frozenset
    payout: int
    center: tuple[int, int]  # in table.png coordinates


# table.png geometry: the number grid starts at (63, 51) and its cells are 45x64,
# dozens sit above it, the even-money bets below it, the "2 to 1" columns to its right
CELL_W, CELL_H = 45, 64
GRID_X, GRID_Y = 63, 51
TABLE_W, TABLE_H = 655, 296
ZERO_CENTER = (31, 147)
DOZEN_Y = GRID_Y // 2
OUTSIDE_Y = (GRID_Y + 3 * CELL_H + TABLE_H) // 2
COLUMN_X = GRID_X + 12 * CELL_W + (TABLE_W - GRID_X - 12 * CELL_W) // 2
CHIP_RADIUS = 17
STACK_STEP = 10  # how far apart the chips of two players on the same spot sit


def number_center(number: int) -> tuple[int, int]:
    """Cell centre of a number. Rows top to bottom are the 3rd, 2nd and 1st column of the table."""
    if number == 0:
        return ZERO_CENTER
    row, col = 2 - (number - 1) % 3, (number - 1) // 3
    return GRID_X + col * CELL_W + CELL_W // 2, GRID_Y + row * CELL_H + CELL_H // 2


def dozen_center(index: int) -> tuple[int, int]:
    return GRID_X + (4 * index + 2) * CELL_W, DOZEN_Y


def outside_center(index: int) -> tuple[int, int]:
    """Even-money bets, two number cells wide each: 1-18, EVEN, RED, black, ODD, 19-36."""
    return GRID_X + (2 * index + 1) * CELL_W, OUTSIDE_Y


def column_center(column: int) -> tuple[int, int]:
    return COLUMN_X, GRID_Y + (3 - column) * CELL_H + CELL_H // 2


def _spots() -> dict[str, Spot]:
    spots = {str(number): Spot(str(number), frozenset({number}), STRAIGHT_PAYOUT, number_center(number))
             for number in ROULETTE_NUMBERS}

    even_money = {
        "1-18": (LOW_NUMBERS, 0), "even": (EVEN_NUMBERS, 1), "red": (RED_NUMBERS, 2),
        "black": (BLACK_NUMBERS, 3), "odd": (ODD_NUMBERS, 4), "19-36": (HIGH_NUMBERS, 5),
    }
    thirds = {
        "1st12": (frozenset(range(1, 13)), dozen_center(0)),
        "2nd12": (frozenset(range(13, 25)), dozen_center(1)),
        "3rd12": (frozenset(range(25, 37)), dozen_center(2)),
        "col1": (frozenset(range(1, 37, 3)), column_center(1)),
        "col2": (frozenset(range(2, 37, 3)), column_center(2)),
        "col3": (frozenset(range(3, 37, 3)), column_center(3)),
    }

    for name, (numbers, index) in even_money.items():
        spots[name] = Spot(name, numbers, EVEN_MONEY_PAYOUT, outside_center(index))
    for name, (numbers, center) in thirds.items():
        spots[name] = Spot(name, numbers, THIRD_PAYOUT, center)
    return spots


SPOTS: dict[str, Spot] = _spots()
NUMBER_SPOTS = [str(number) for number in ROULETTE_NUMBERS]


def describe_number(number: int) -> str:
    if number == 0:
        return "zero"
    colour = "red" if number in RED_NUMBERS else "black"
    return f"{colour} {'odd' if number % 2 else 'even'} {'1-18' if number < 19 else '19-36'}"


def short_amount(amount: int) -> str:
    return f"{amount // 1000}k" if amount >= 1000 and amount % 1000 == 0 else str(amount)


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

# one color per player, so a shared table can tell the chips — and the caption lines — apart, BGR
PLAYER_COLOURS = [(80, 80, 235), (80, 190, 120), (80, 195, 235), (200, 100, 200), (225, 195, 90), (90, 135, 235)]
PLAYER_DOTS = ["🟥", "🟩", "🟨", "🟪", "🟦", "🟧"]


def player_colour(index: int) -> tuple[int, int, int, int]:
    return PLAYER_COLOURS[index % len(PLAYER_COLOURS)] + (255,)


def player_dot(index: int) -> str:
    return PLAYER_DOTS[index % len(PLAYER_DOTS)]


def draw_chip(frame: np.ndarray, center: tuple[int, int], amount: int, colour=GOLDEN) -> None:
    """A chip with the stake on it, dropped on the cell that is bet on."""
    x, y = center[0] + table_pad_x, center[1] + table_pad_y
    cv2.circle(frame, (x, y), CHIP_RADIUS, colour, -1)
    cv2.circle(frame, (x, y), CHIP_RADIUS, WHITE, 2)
    put_rotated_text(frame, short_amount(amount), (x, y + 5), 0, BLACK)


def draw_wheel(frame: np.ndarray, wheel_angle: float = 0.0, ball_angle: float = None) -> None:
    """The wheel on top of the frame, with the ball on its rim when an angle is given."""
    rotation_matrix = cv2.getRotationMatrix2D(wheel_center, -wheel_angle, 1)
    wheel = cv2.warpAffine(wheel_original, rotation_matrix, wheel_size, cv2.INTER_LINEAR)
    if ball_angle is not None:
        draw_ball(wheel, wheel_center, int(wheel_center[0] * 0.75) + 2, ball_angle)
    cv2_paste_with_alpha(frame, wheel, (wheel_pad_x, wheel_pad_y))


def render_table(chips: list[tuple[str, int, tuple]] = (), wheel: bool = False) -> np.ndarray:
    """The betting table with a chip on every covered spot.

    `chips` are `(spot name, amount, colour)`. Chips of several players on the same spot are spread
    along a short diagonal across the cell, so that every one of them stays visible. With `wheel`
    the wheel is drawn above the table, which is what the players bet against.
    """
    frame = background.copy()
    cv2_paste_with_alpha(frame, table, (table_pad_x, table_pad_y))

    stack: dict[str, int] = {name: sum(1 for chip in chips if chip[0] == name) for name, _, _ in chips}
    drawn: dict[str, int] = {}
    for name, amount, colour in chips:
        index = drawn.get(name, 0)
        drawn[name] = index + 1
        shift = int((index - (stack[name] - 1) / 2) * STACK_STEP)
        x, y = SPOTS[name].center
        draw_chip(frame, (x + shift, y - shift), amount, colour)

    if wheel:
        draw_wheel(frame)

    return frame


def render_roulette(winning_number: int = None, chips: list[tuple[str, int, tuple]] = (),
                    total_seconds: float = None) -> tuple[str, float, int]:
    fps = 30
    total_seconds = float(total_seconds if total_seconds is not None else np.random.uniform(8.0, 12.0))
    if winning_number is None:
        winning_number = int(np.random.choice(ROULETTE_NUMBERS))
    filename = tmp_folder_path / f'roulette_{np.random.randint(0, 1 << 31)}.mp4'

    angles = generate_roulette_angles(winning_number, total_seconds, fps)
    table_frame = render_table(chips)

    with OpencvCustomWriter(fps, WIDTH, HEIGHT, filename) as writer:
        for wheel_angle, ball_angle in angles:
            img = table_frame.copy()
            draw_wheel(img, wheel_angle, ball_angle)
            # cv2.imshow("wheel", img)
            # cv2.waitKey(1000 // fps)
            writer.write(img)

    return filename, total_seconds, winning_number


if __name__ == '__main__':
    _, seconds, win = render_roulette()
    print(seconds, win)
