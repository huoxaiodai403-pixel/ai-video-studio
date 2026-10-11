"""Blender-only worker: create an editable, deterministic geometric camera rehearsal."""
import json
import math
from pathlib import Path
import sys


def main():
    import bpy
    from mathutils import Vector
    source, output = sys.argv[sys.argv.index('--')+1:]
    spec = json.loads(Path(source).read_text(encoding='utf-8'))
    dest = Path(output); (dest/'frames').mkdir(exist_ok=True)
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    # Workbench gives useful white-model geometry without CUDA/model contention.
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x = spec['width']; scene.render.resolution_y = spec['height']
    scene.render.resolution_percentage = 100
    scene.render.fps = spec['fps']
    scene.frame_start = 1; scene.frame_end = max(1, round(spec['duration']*spec['fps']))
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'OBJECT'
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.background_type = 'WORLD'
    scene.world.color = (.075, .09, .12)
    bpy.ops.mesh.primitive_plane_add(size=40)
    bpy.context.object.name = 'Ground'; bpy.context.object.color = (.25, .28, .33, 1)
    objects = spec['objects'] or [{'name': 'Subject', 'shape': spec['subject'], 'start': [0,0,1], 'end': [0,0,1], 'scale': [1,1,1]}]
    for index, item in enumerate(objects):
        if item['shape'] == 'sphere':
            bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, location=item['start'])
        elif item['shape'] == 'cylinder':
            bpy.ops.mesh.primitive_cylinder_add(vertices=24, location=item['start'])
        else:
            bpy.ops.mesh.primitive_cube_add(location=item['start'])
        obj = bpy.context.object; obj.name = item['name']; obj.scale = item['scale']
        obj.color = [(.8,.85,.9,1),(.2,.65,.7,1),(.9,.55,.3,1)][index%3]
        obj.keyframe_insert(data_path='location', frame=1)
        obj.location = item['end']; obj.keyframe_insert(data_path='location', frame=scene.frame_end)
    bpy.ops.object.camera_add()
    camera = bpy.context.object; camera.name = 'PrevisCamera'; camera.data.lens = 42; scene.camera = camera
    target = Vector((0,0,1))
    # Per-frame keys avoid any version-dependent interpolation or wall-clock playback.
    for frame in range(1, scene.frame_end+1):
        t = (frame-1)/max(1,scene.frame_end-1)
        angle = -.85 + (1.2*t if spec['camera'] == 'orbit' else 0)
        distance = spec['distance']*(1-.35*t if spec['camera'] == 'push' else 1)
        camera.location = (math.sin(angle)*distance, -math.cos(angle)*distance, 3)
        camera.rotation_euler = (target-camera.location).to_track_quat('-Z','Y').to_euler()
        camera.keyframe_insert(data_path='location',frame=frame)
        camera.keyframe_insert(data_path='rotation_euler',frame=frame)
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = str(dest/'frames/frame-')
    # Five hashes yield fixed numbered frame files.
    scene.render.filepath += '#####'
    bpy.ops.wm.save_as_mainfile(filepath=str(dest/'scene.blend'))
    bpy.ops.render.render(animation=True)


if __name__ == '__main__':
    main()
