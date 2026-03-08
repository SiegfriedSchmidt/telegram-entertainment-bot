from matplotlib import animation
from lib.init import galton_videos_folder_path, galton_assets_folder_path
from lib.logger import main_logger
from lib.opencv_custom_writer import OpencvCustomWriter
from lib.storage import storage
from typing import Any
import os
import numpy as np
import matplotlib.pyplot as plt
import pymunk
import math
import time
import cv2

_viridis_colors = plt.get_cmap('viridis')(np.linspace(0, 1, 256))[:, :3]


class BallCollisionData:
    def __init__(self, path: int, path_size: int, ball_id: int):
        self.path = path
        self.path_size = path_size
        self.ball_id = ball_id
        self.decided_pegs: set[pymunk.Vec2d] = set()
        self.path_idx = 0

    def __get_val_by_idx(self, idx: int) -> bool:
        return bool((1 << idx) & self.path)

    def get_direction(self) -> int:
        direction = self.__get_val_by_idx(self.path_idx)
        self.path_idx += 1
        return int(direction) * 2 - 1

    def get_path(self) -> str:
        path_str = ''
        for i in range(self.path_size):
            path_str += '1' if self.__get_val_by_idx(i) else '0'
        return path_str


class PhysicsSimulation:
    def __init__(self, seed: int = None):
        self.space_gravity = 0, -9.81
        self.space_damping = 0.995
        self.space_threaded = False
        self.space_threads = 1
        self.width, self.height = 18, 14
        self.e = 0.3  # Elasticity of objects.  Must be <=1.
        self.friction = 0.2
        self.T = 14  # how long to simulate?
        self.dt = 1 / 300  # we simulate 300 timesteps per second
        self.subsampling = 10  # render one out of this number of timesteps.
        self.dpi = 40  # use low values for preview. dpi=120 yields fullhd video if width,height are 16,9
        self.r = 0.15
        self.R = 0.2
        self.gap = self.r * 2 + self.R * 2 + 0.2
        self.v_rand = 0
        self.pos_rand = 0
        self.rows = 16
        self.DYNAMIC_CATEGORY = 1  # 2 ** 0
        self.STATIC_CATEGORY = 2  # 2 ** 1
        self.lowest_x, self.lowest_y, self.columns = 0, 0, 0
        self.seed = np.random.randint((1 << 63) - 1) if seed is None else seed
        self.random = np.random.default_rng(self.seed)
        self.interval = self.dt * self.subsampling
        self.fps = int(1 / self.interval)
        self.manual_coefficients = np.array([999, 400, 30, 9.5, 3, 1, 0.5, 0.2, 0, 0.2, 0.5, 1, 3, 9.5, 30, 400, 999])

    def setup_space(self, balls_count: int) -> tuple[pymunk.Space, list[pymunk.Body]]:
        space = pymunk.Space(threaded=self.space_threaded)

        space.gravity = self.space_gravity
        space.damping = self.space_damping
        space.threads = self.space_threads
        static_body = space.static_body

        # Filter for dynamic shapes (only collides with static)
        dynamic_filter = pymunk.ShapeFilter(
            categories=self.DYNAMIC_CATEGORY,  # what I am
            mask=self.STATIC_CATEGORY  # what I collide with
        )

        # Filter for static shapes (collides with dynamic)
        # Usually you don't even need to set this one explicitly
        static_filter = pymunk.ShapeFilter(
            categories=self.STATIC_CATEGORY,
            mask=self.DYNAMIC_CATEGORY  # can be just 0xFFFFFFFF too
        )

        static_lines = [
            # Bottom floor
            # pymunk.Segment(static_body, (0, 0), (self.width, 0), 0.01),
            # Right wall
            # pymunk.Segment(static_body, (self.width - gap, gap), (self.width - gap, self.height * 100), 0.01),
            # Left wall
            # pymunk.Segment(static_body, (gap, gap), (gap, self.height * 100), 0.01),
            # pymunk.Segment(static_body, (0, self.height), (self.width / 2 - 1, self.height / 2), 0.01),
            # pymunk.Segment(static_body, (self.width, self.height), (self.width / 2 + 1, self.height / 2), 0.01),
            # pymunk.Segment(static_body, (0, 0), (self.width / 2 - 1, self.height / 2), 0.01),
            # pymunk.Segment(static_body, (self.width, 0), (self.width / 2 + 1, self.height / 2), 0.01),
        ]

        static_circles: list[pymunk.Circle] = []

        cy = self.height - 1.5
        self.lowest_y = cy - (self.rows - 1) * self.gap * np.sqrt(3) / 2
        for row in range(self.rows):
            y = cy - row * self.gap * np.sqrt(3) / 2
            # row2 = rows - 1 + row % 2
            row2 = row
            for col in range(row2 + 1):
                x = self.width / 2 - self.gap / 2 * row2 + self.gap * col
                shape = pymunk.Circle(static_body, self.r, (x, y))
                shape.elasticity = self.e
                shape.friction = self.friction
                shape.filter = static_filter
                shape.collision_type = self.STATIC_CATEGORY
                static_circles.append(shape)
                if row == self.rows - 1:
                    static_lines.append(pymunk.Segment(static_body, (x, y - self.r), (x, 0), self.r))
                    if col == 0:
                        self.columns = row2
                        self.lowest_x = x

        for line in static_lines:
            # line.elasticity = self.e
            line.friction = 0.5
            line.filter = static_filter
        space.add(*static_lines, *static_circles)

        balls: list[pymunk.Body] = []

        for i in range(balls_count):
            body = pymunk.Body(0, 0)
            body.position = (
                self.width / 2 + self.random.uniform(-self.pos_rand, self.pos_rand),
                cy + self.r + self.R + 1
            )
            body.velocity = self.random.uniform(-self.v_rand, self.v_rand), 0
            body.radius = self.R

            shape = pymunk.Circle(body, self.R)
            shape.density = 1
            shape.elasticity = self.e
            shape.friction = self.friction
            shape.filter = dynamic_filter
            shape.collision_type = self.DYNAMIC_CATEGORY

            space.add(body, shape)
            balls.append(body)

        return space, balls

    def simulate(self, space: pymunk.Space, balls: list[pymunk.Body]) -> \
            tuple[list[list[np.ndarray[tuple[Any, ...]]]], list[int], list[int]]:
        positions: list[list[np.ndarray[tuple[Any, ...]]]] = []
        ball_category = [0 for _ in range(len(balls))]
        categories_count = [0 for _ in range(self.columns + 2)]
        resolved_count = 0

        last_part = 0
        for t in np.arange(0, self.T, self.dt):
            cur_part = t / self.T
            if cur_part - last_part >= 0.02:
                last_part = cur_part
                # print(f'Simulation: {cur_part:.1%}, resolved: {resolved_count}')
            # log ball positions
            positions.append([np.array(b.position) for b in balls])
            # Step the simulation
            space.step(self.dt)
            for i, b in enumerate(balls):
                if b in space.bodies:
                    if not ball_category[i] and b.position[1] <= self.R:
                        x_with_offset = b.position[0] - self.lowest_x
                        category = int(x_with_offset / self.gap) + 2
                        if x_with_offset < 0:
                            category = 1
                        elif category >= self.columns + 2:
                            category = self.columns + 2

                        ball_category[i] = category
                        categories_count[category - 1] += 1
                        resolved_count += 1

                        # shape = list(b.shapes)[0]
                        # shape.filter = pymunk.ShapeFilter(group=0)
                    if b.position[1] < 0 or ball_category[i]:
                        shape = list(b.shapes)[0]
                        space.remove(b, shape)
            if len(space.bodies) == 0 or resolved_count == len(balls):
                break
        return positions, ball_category, categories_count

    @staticmethod
    def calculate_dist_params(probabilities: np.ndarray, values: np.ndarray = None) -> tuple[float, float]:
        if values is None:
            values = np.arange(probabilities.size)
        E = np.sum(values * probabilities)
        E2 = np.sum(values ** 2 * probabilities)
        Var = E2 - E ** 2
        return E, Var

    def compute_probabilities(self, categories_count: list[int]):
        categories_count = np.array(categories_count)
        resolved_count = np.sum(categories_count)
        probabilities = categories_count / resolved_count
        E, Var = self.calculate_dist_params(probabilities)
        Expected_Var = self.rows * 0.5 * 0.5
        print(
            f"{len(categories_count)=}\n{resolved_count=}\n{categories_count=}\n{probabilities=}\n{E=}\n{Var=}\n{Expected_Var=}"
        )

        bin_probabilities = np.zeros_like(probabilities)
        for x in range(1, bin_probabilities.size - 1):
            bin_probabilities[x] = math.comb(self.rows, x) * 0.5 ** self.rows
        bin_probabilities[0] = (1 - np.sum(bin_probabilities)) / 2
        bin_probabilities[-1] = bin_probabilities[0]

        bin_E, bin_Var = self.calculate_dist_params(bin_probabilities)
        coefficients = 1 / bin_probabilities / bin_probabilities.size
        print('IDEAL coefficients:', list(map(float, coefficients)))

        print(self.manual_coefficients * bin_probabilities)
        coef_E, coef_Var = self.calculate_dist_params(bin_probabilities, self.manual_coefficients)
        bin_probabilities = list(map(float, bin_probabilities))
        manual_coefficients = list(map(float, self.manual_coefficients))
        print(f"{manual_coefficients=}\n{bin_probabilities=}\n{coef_E=}\n{coef_Var=}\n{bin_E=}\n{bin_Var=}")

    def prepare_ball_collisions_data(self, balls: list[pymunk.Body], predefined_paths: list[int] = None) -> \
            tuple[dict[int, BallCollisionData], list[BallCollisionData]]:
        ball_collisions_data = dict()
        ball_collisions_list = list()
        for i, ball_body in enumerate(balls):
            path = int(self.random.integers(0, 2 ** self.rows)) if predefined_paths is None else predefined_paths[i]
            ball_data = BallCollisionData(path, self.rows, i)
            ball_collisions_data[ball_body.id] = ball_data
            ball_collisions_list.append(ball_data)

        return ball_collisions_data, ball_collisions_list

    def set_pre_solve_for_balls_collisions(self, space: pymunk.Space,
                                           ball_collisions_data: dict[int, BallCollisionData]):
        def pre_solve_ball(arbiter: pymunk.Arbiter, space: pymunk.Space, data: Any):
            ball, peg = arbiter.shapes
            peg_pos: pymunk.Vec2d = peg.offset

            if isinstance(data, dict):
                ball_data: BallCollisionData = data[ball.body.id]
            else:
                raise ValueError("Data must be a list")

            if peg_pos not in ball_data.decided_pegs:
                direction = ball_data.get_direction()
                ball.body.velocity = (1 * direction, 0)
                ball_data.decided_pegs.add(peg_pos)

        space.on_collision(self.DYNAMIC_CATEGORY, self.STATIC_CATEGORY, pre_solve=pre_solve_ball,
                           data=ball_collisions_data)

    def prepare_figure(self) -> tuple[plt.Figure, plt.Axes]:
        fig, ax = plt.subplots(figsize=(self.width, self.height), dpi=self.dpi)
        ax.set(xlim=[0, self.width], ylim=[0, self.height])
        ax.set_aspect("equal")
        ax.set_position((0, 0, 1, 1))
        fig.set(facecolor="y")
        return fig, ax

    @staticmethod
    def prepare_patches(balls: list[pymunk.Body], ball_category: list[int], len_categories: int) -> list[plt.Circle]:
        cmap = plt.get_cmap("viridis")
        circles = [
            plt.Circle(
                xy=(0, 0),
                radius=b.radius,
                facecolor=cmap((ball_category[i] - 1) / (len_categories - 1)) if ball_category[i] != 0 else "b"
            ) for i, b in enumerate(balls)
        ]
        return circles

    def prepare_background(self, ax: plt.Axes, space: pymunk.Space, len_categories: int):
        # ax.set_facecolor((176 / 255, 196 / 255, 177 / 255))
        # ax.set_facecolor((73 / 255, 151 / 255, 208 / 255))
        # ax.set_facecolor((97 / 255, 64 / 255, 81 / 255))
        ax.set_facecolor((140 / 255, 146 / 255, 172 / 255))

        categories_middle = (len_categories - 1) / 2
        cmap = plt.get_cmap("autumn")
        for s in space.static_body.shapes:
            if isinstance(s, pymunk.Circle):
                ax.add_patch(plt.Circle((s.offset.x, s.offset.y), radius=s.radius, facecolor='black'))
            elif isinstance(s, pymunk.Segment):
                idx = np.floor(abs(s.a.x - self.lowest_x - categories_middle * self.gap + 0.5 * self.gap) / self.gap)
                color = cmap(idx / (categories_middle - 1))
                ax.plot([s.a.x, s.b.x], [s.a.y, s.b.y], linewidth=s.radius * self.dpi, color=color)

        for i, coef in enumerate(self.manual_coefficients):
            color = cmap(abs(categories_middle - i) / categories_middle)
            ax.text(
                self.lowest_x + self.gap * i - self.gap * 0.5, self.lowest_y - 0.5, f'{coef:g}',
                fontsize=21,
                color=color,
                fontweight='bold',
                horizontalalignment='center',
                verticalalignment='center'
            )

    def render(self, fig: plt.Figure, circles: list[plt.Circle], frames: list[list[np.ndarray[tuple[Any, ...]]]],
               filename: str):
        cur_frame = [-3]

        # Animation function. This is called for each frame, passing an entry in positions
        def draw_frame(p: list[tuple[float, float]]):
            # cur_frame[0] += 1
            # if cur_frame[0] % 10 == 0 or cur_frame[0] >= frames_count:
            #     print(f'Frame: {cur_frame[0]}/{frames_count}')
            for i, c in enumerate(circles):
                c.set_center(p[i])
            return circles

        anim = animation.FuncAnimation(
            fig,
            draw_frame,
            frames=frames,
            interval=self.interval * 1000,
            blit=True
        )

        # print(f"Rendering {frames_count} frames at {fps} fps")

        FFwriter = animation.FFMpegWriter(fps=self.fps)
        anim.save(filename, writer=FFwriter)
        plt.close(fig)

    @staticmethod
    def autumn_cmap(t: float):
        return 255, int(round(t * 255)), 0

    @staticmethod
    def viridis_cmap(t: float):
        idx = int(round(t * (len(_viridis_colors) - 1)))
        return _viridis_colors[idx] * 255

    def prepare_ball_colors(self, ball_category: list[int], len_categories: int) -> list[tuple[int, int, int]]:
        ball_colors = list()
        categories_middle = (len_categories - 1) / 2
        for i, category in enumerate(ball_category):
            t = (abs(category - 1 - categories_middle) / categories_middle)
            R, G, B = self.viridis_cmap(t)
            ball_colors.append((B, G, R))
        return ball_colors

    def write_frames(self, writer: cv2.VideoWriter, frames: list[list[np.ndarray[tuple[Any, ...]]]],
                     ball_colors: list[tuple[int, int, int]], width: int, height: int, background_path: str = None):
        if not writer.isOpened():
            writer.release()
            raise RuntimeError("cv2.VideoWriter failed to open")
        if background_path is None:
            background_path = galton_assets_folder_path / "background.png"
        if not os.path.exists(background_path):
            self.save_background(background_path)

        background = cv2.imread(background_path)
        cv2.putText(background, str(len(ball_colors)), (7, 80), cv2.FONT_HERSHEY_SIMPLEX, 3, (255, 255, 255), 2,
                    cv2.LINE_AA)
        for circle in frames:
            frame = background.copy()
            for idx, pos in enumerate(circle):
                center = int(np.round(pos[0] * self.dpi)), int(np.round(height - pos[1] * self.dpi))
                cv2.circle(frame, center, int(self.R * self.dpi), ball_colors[idx], -1, lineType=cv2.LINE_AA)
            writer.write(frame)

        writer.release()

    def render_opencv(self, frames: list[list[np.ndarray[tuple[Any, ...]]]], ball_colors: list[tuple[int, int, int]],
                      filename: str, background_path: str = None):
        width, height = int(self.width * self.dpi), int(self.height * self.dpi)

        with OpencvCustomWriter(self.fps, width, height, filename) as writer:
            self.write_frames(writer, frames, ball_colors, width, height, background_path)

    def save_background(self, filename: str):
        space, balls = self.setup_space(1)
        ball_collisions_data, ball_collisions_list = self.prepare_ball_collisions_data(balls)
        self.set_pre_solve_for_balls_collisions(space, ball_collisions_data)
        positions, ball_category, categories_count = self.simulate(space, balls)
        fig, ax = self.prepare_figure()
        self.prepare_background(ax, space, len(categories_count))
        plt.savefig(filename)

    def run(self, balls_count: int = 1) -> tuple[float, str, float]:
        t = time.monotonic()

        space, balls = self.setup_space(balls_count)
        ball_collisions_data, ball_collisions_list = self.prepare_ball_collisions_data(balls)
        self.set_pre_solve_for_balls_collisions(space, ball_collisions_data)
        positions, ball_category, categories_count = self.simulate(space, balls)

        assert len(categories_count) == self.manual_coefficients.size, "Inconsistent number of categories"
        # self.compute_probabilities(categories_count)

        filename = galton_videos_folder_path / f"{self.seed}.mp4"
        multiplier = np.round(np.sum(np.array(categories_count) * self.manual_coefficients), 1)
        frames = positions[::self.subsampling]
        ball_colors = self.prepare_ball_colors(ball_category, len(categories_count))

        self.render_opencv(frames, ball_colors, filename)

        main_logger.info(
            f"Galton simulation completed in {time.monotonic() - t:.3f} seconds" +
            (" (ffmpeg used)" if storage.ffmpeg_use else "")
        )
        return float(multiplier), filename, len(frames) * self.interval

    def run_predefined(self, predefined_paths: list[int]):
        space, balls = self.setup_space(len(predefined_paths))
        ball_collisions_data, ball_collisions_list = self.prepare_ball_collisions_data(balls, predefined_paths)
        self.set_pre_solve_for_balls_collisions(space, ball_collisions_data)
        positions, ball_category, categories_count = self.simulate(space, balls)

        collision_data = ball_collisions_list[0]
        filename = galton_videos_folder_path / f"{collision_data.get_path()}.mp4"
        frames = positions[::self.subsampling]
        ball_colors = self.prepare_ball_colors(ball_category, len(categories_count))

        self.render_opencv(frames, ball_colors, filename)


if __name__ == '__main__':
    physics_simulation = PhysicsSimulation()
    # physics_simulation.save_background(galton_folder_path / "background.png")
    paths = ["0" * (16 - i) + "1" * i for i in range(17)]
    paths = [int(p, 2) for p in paths]
    physics_simulation.run(222)
    # physics_simulation.run_predefined(paths)
