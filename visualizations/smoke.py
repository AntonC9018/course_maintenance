from manim import DOWN, FadeIn, MathTex, Scene, Text, Write


class Smoke(Scene):
    """Headless proof that Manim, LaTeX, dvisvgm, and ffmpeg work."""

    def construct(self):
        formula = MathTex(r"b = a + 6 = 11")
        note = Text("visualization toolchain", font_size=28).next_to(formula, DOWN)
        self.play(Write(formula), FadeIn(note))
        self.wait(0.5)
