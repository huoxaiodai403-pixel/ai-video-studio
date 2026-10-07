"""Narration-timed diagram animation; inspired by the archived whiteboard article."""
import json
import os
from pathlib import Path
from manim import *

class NarratedBoard(Scene):
    def construct(self):
        self.camera.background_color='#F7F4EC'
        project=Path(os.environ['BOARD_PROJECT'])
        spec=json.loads((project/'storyboard.json').read_text(encoding='utf-8'))
        timing=json.loads((project/'timeline.json').read_text(encoding='utf-8'))
        for index,(scene,clock) in enumerate(zip(spec['scenes'],timing)):
            self.clear()
            title=Text(scene.get('board_title',spec.get('title','科普讲解')),font='Microsoft YaHei',font_size=36,color='#18364A')
            if title.width>12:title.scale_to_fit_width(12)
            title.to_edge(UP,buff=.6);self.add(title)
            labels=scene.get('board_cards',['内容','画面','声音'])[:3]
            group=VGroup()
            for i,label in enumerate(labels):
                rect=RoundedRectangle(width=3.4,height=1.7,corner_radius=.15,color='#287C8E',stroke_width=4)
                text=Text(label,font='Microsoft YaHei',font_size=30,color='#18364A')
                if text.width>2.9:text.scale_to_fit_width(2.9)
                cell=VGroup(rect,text).move_to([(i-(len(labels)-1)/2)*4.1,.3,0]);group.add(cell)
            beat=clock['duration']/len(group)
            for i,cell in enumerate(group):
                motions=[Create(cell[0]),Write(cell[1])]
                if i:
                    arrow=Arrow(group[i-1].get_right(),cell.get_left(),buff=.1,color='#DB9353')
                    motions.append(GrowArrow(arrow))
                self.play(*motions,run_time=min(.9,beat*.65))
                self.wait(max(.01,beat-min(.9,beat*.65)))
