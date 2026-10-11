from manim import *


class WaveDemo(Scene):
    def construct(self):
        self.camera.background_color = '#111820'
        title = Text('波的传播', font='Microsoft YaHei', font_size=46, color=WHITE).to_edge(UP)
        subtitle = Text('波形向前传播，介质中的点在原位振动', font='Microsoft YaHei', font_size=25, color='#b6c9d8').to_edge(DOWN)
        axes = Axes(x_range=[-6,6,1], y_range=[-2,2,1], x_length=11, y_length=3.6, tips=False, axis_config={'color':'#60778d','include_ticks':False})
        phase = ValueTracker(0)
        wave = always_redraw(lambda: axes.plot(lambda x: np.sin(x-phase.get_value()), color='#82dbc5'))
        dot = always_redraw(lambda: Dot(axes.c2p(0,np.sin(-phase.get_value())),color='#ffd580',radius=.12))
        guide = DashedLine(axes.c2p(0,-1.5),axes.c2p(0,1.5),color='#60778d')
        self.add(title,subtitle,axes,guide,wave,dot)
        self.play(phase.animate.set_value(4*PI),run_time=8,rate_func=linear)
        self.wait(1)
