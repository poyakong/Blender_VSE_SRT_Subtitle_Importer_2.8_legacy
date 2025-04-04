bl_info = {
    "name": "SRT Subtitle Importer/Exporter",
    "author": "poyakong",
    "version": (0, 0, 2),
    "blender": (3, 0, 0),
    "location": "Sequencer > SRT, Sequencer > Sidebar > SRT",
    "description": "Import/Export SRT subtitle files to/from VSE strips",
    "category": "Sequencer",
}

# import bpy for Blender Python API
import bpy
# import re from the Python standard library, for regular expressions
import re
# import os for file path handling
import os
# import props for custom properties
from bpy.props import StringProperty, IntProperty, FloatProperty, BoolProperty, EnumProperty, PointerProperty
# import operators for custom operators
from bpy.types import Operator, Menu, Panel, PropertyGroup
# import io_utils for custom import/export operators
from bpy_extras.io_utils import ImportHelper, ExportHelper

# SRT time format: 00:00:00,000
def parse_srt_time(time_str):
    # Convert SRT time format to seconds
    hours, minutes, seconds = time_str.replace(',', '.').split(':')
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)

def format_srt_time(seconds):
    # Convert seconds to SRT time format
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = seconds % 60
    milliseconds = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{int(seconds):02d},{milliseconds:03d}"

# Get scene FPS
def get_scene_fps(scene):
    fps = scene.render.fps / scene.render.fps_base
    return fps

# Get text strips for template dropdown
def get_text_strips(scene, context):
    items = []
    if scene and scene.sequence_editor:
        for i, seq in enumerate(scene.sequence_editor.sequences_all):
            if seq.type == 'TEXT':
                items.append((str(i), seq.name, f"Use {seq.name} as template"))
    
    if not items:
        items.append(('NONE', "No Text Strips", "No text strips available"))
    
    return items

# Modified SRT Properties class
class SRTProperties(PropertyGroup):
    template_name: StringProperty(
        name="Subtitle Name",
        description="Template name for batch subtitle creation",
        default="Subtitle {index}"
    )
    
    template_strip: StringProperty(
        name="Text Template",
        description="Select a text strip to use as template"
    )

# Operators
class SEQUENCER_OT_ImportSRT(Operator, ImportHelper):
    bl_idname = "sequencer.import_srt"
    bl_label = "Import SRT"
    bl_description = "Import subtitles from SRT file"
    
    filename_ext = ".srt"
    filter_glob: StringProperty(default="*.srt", options={'HIDDEN'})
    
    start_frame: IntProperty(
        name="Start Frame",
        description="Frame to start placing subtitles",
        default=1
    )

    subtitle_channel: IntProperty(
    name="Subtitle Channel",
    description="Channel to generate subtitles",
    default=1,
    min=1,
    max=32  # Not recommand user to use any channel over 32
    )
    
    use_scene_fps: BoolProperty(
        name="Use Scene FPS",
        description="Use the scene's FPS setting instead of a custom value",
        default=True
    )
    
    custom_fps: FloatProperty(
        name="Custom FPS",
        description="Custom frames per second for conversion (only used if 'Use Scene FPS' is off)",
        default=24.0,
        min=1.0
    )
    
    def draw(self, context):
        layout = self.layout
        
        layout.prop(self, "start_frame")
        layout.prop(self, "use_scene_fps")
        
        # Only show custom FPS option if use_scene_fps is off
        if not self.use_scene_fps:
            layout.prop(self, "custom_fps")
        else:
            # Display the current scene FPS (read-only)
            fps = get_scene_fps(context.scene)
            layout.label(text=f"Current Scene FPS: {fps:.3f}")

        layout.prop(self, "subtitle_channel")
    
    def execute(self, context):
        try:
            # Determine which FPS to use
            if self.use_scene_fps:
                fps = get_scene_fps(context.scene)
            else:
                fps = self.custom_fps
            
            # Open and read the SRT file
            with open(self.filepath, 'r', encoding='utf-8-sig') as file:
                content = file.read()
            
            # Regular expression to parse SRT file
            # Matches each subtitle entry, with the following groups:
            # 1: index (Multiple digits)
            # 2: start time (HH:MM:SS,MMM)
            # 3: end time (HH:MM:SS,MMM)
            # 4: text (Texts until [a digits with a newline] or [EOF])
            pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n([\s\S]*?)(?=\n\n\d+\n|$)'
            matches = re.findall(pattern, content)
            
            if not matches:
                self.report({'ERROR'}, "No subtitles found in the SRT file")
                return {'CANCELLED'}
            
            # Get the current sequence editor
            scene = context.scene
            if not scene.sequence_editor:
                scene.sequence_editor_create()
            
            seq_editor = scene.sequence_editor
            
            # Check if a text template is selected
            template_strip = None
            template_name = context.scene.srt_props.template_name
            template_strip_name = context.scene.srt_props.template_strip
        
            # Try to get the text template by name
            if template_strip_name and template_strip_name in seq_editor.sequences_all:
                template_strip = seq_editor.sequences_all[template_strip_name]
            
            # Add each subtitle as a text strip
            for index, start_time, end_time, text in matches:
                # Convert times to seconds
                start_sec = parse_srt_time(start_time)
                end_sec = parse_srt_time(end_time)
                
                # Convert seconds to frames
                start_frame = int(self.start_frame + start_sec * fps)
                end_frame = int(self.start_frame + end_sec * fps)
                duration = end_frame - start_frame
                
                # Clean up text (remove extra newlines at end)
                text = text.strip()
                
                # Format the name using the template
                strip_name = f"{template_name.replace('{index}', str(index))}"

                '''
                # old version of lyric text strip generator (stable)
                
                # Create text strip
                text_strip = seq_editor.sequences.new_effect(
                    name=strip_name,
                    type='TEXT',
                    channel=self.subtitle_channel,
                    frame_start=start_frame,
                    frame_end=start_frame + duration
                )
                
                # Set text properties
                text_strip.text = text
                
                # Apply template properties if text template is selected
                if template_strip and template_strip.type == 'TEXT':
                    # Copy properties from template
                    text_strip.font_size = template_strip.font_size
                    text_strip.location = template_strip.location
                    text_strip.use_bold = template_strip.use_bold
                    text_strip.use_italic = template_strip.use_italic
                    text_strip.use_shadow = template_strip.use_shadow
                    text_strip.shadow_color = template_strip.shadow_color
                    text_strip.blend_type = template_strip.blend_type
                    
                    # Copy alignment if available
                    if hasattr(template_strip, 'text_align') and hasattr(text_strip, 'text_align'):
                        text_strip.text_align = template_strip.text_align
                else:
                    # Default settings
                    text_strip.font_size = 24
                    text_strip.location[1] = 0.1  # Y location (vertical position)
                    text_strip.use_bold = False
                    text_strip.use_italic = False
                    text_strip.use_shadow = True
                    text_strip.shadow_color = (0, 0, 0, 1)  # Black shadow
                    text_strip.blend_type = 'ALPHA_OVER'
                    
                    # TextSequence doesn't have align_x, but we can set alignment in Blender ≥ 2.8
                    # with the 'text_align' property if it exists
                    if hasattr(text_strip, 'text_align'):
                        text_strip.text_align = 'CENTER'
                '''

                # New version of lyric text strip generator by duplicating the template (more accurate results, but unexpected behavior may occur)
                if template_strip and template_strip.type == 'TEXT':
                    # Duplicate the template strip
                    bpy.ops.sequencer.select_all(action='DESELECT')
                    template_strip.select = True
                    context.scene.sequence_editor.active_strip = template_strip
                    
                    # Duplicate the strip
                    bpy.ops.sequencer.duplicate()
                    
                    # Get the newly created strip (should be the selected one)
                    text_strip = context.selected_sequences[0]
                    
                    # Update the new strip properties
                    text_strip.name = strip_name
                    text_strip.text = text
                    text_strip.frame_start = start_frame
                    text_strip.frame_final_end = start_frame + duration
                    text_strip.channel = self.subtitle_channel
                else:
                    # Create new text strip if no template
                    text_strip = seq_editor.sequences.new_effect(
                        name=strip_name,
                        type='TEXT',
                        channel=self.subtitle_channel,
                        frame_start=start_frame,
                        frame_end=start_frame + duration
                    )
                    
                    # Set text properties
                    text_strip.text = text
                    
                    # Default settings
                    text_strip.font_size = 24
                    text_strip.location[1] = 0.1  # Y location (vertical position)
                    text_strip.use_bold = False
                    text_strip.use_italic = False
                    text_strip.use_shadow = True
                    text_strip.shadow_color = (0, 0, 0, 1)  # Black shadow
                    text_strip.blend_type = 'ALPHA_OVER'
                    
                    # TextSequence doesn't have align_x, but we can set alignment in Blender ≥ 2.8
                    # with the 'text_align' property if it exists
                    if hasattr(text_strip, 'text_align'):
                        text_strip.text_align = 'CENTER'
                
            # Get file name
            filename = os.path.basename(self.filepath)
            self.report({'INFO'}, f"Success. From [{filename}] there are [{len(matches)}] subtitles imported using FPS: [{fps:.3f}]")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error importing SRT: {str(e)}")
            return {'CANCELLED'}

class SEQUENCER_OT_ExportSRT(Operator, ExportHelper):
    bl_idname = "sequencer.export_srt"
    bl_label = "Export SRT"
    bl_description = "Export selected text strips as SRT file"
    
    filename_ext = ".srt"
    filter_glob: StringProperty(default="*.srt", options={'HIDDEN'})
    
    use_scene_fps: BoolProperty(
        name="Use Scene FPS",
        description="Use the scene's FPS setting instead of a custom value",
        default=True
    )
    
    custom_fps: FloatProperty(
        name="Custom FPS",
        description="Custom frames per second for conversion (only used if 'Use Scene FPS' is off)",
        default=24.0,
        min=1.0
    )
    
    def draw(self, context):
        layout = self.layout
        
        layout.prop(self, "use_scene_fps")
        
        # Only show custom FPS option if use_scene_fps is off
        if not self.use_scene_fps:
            layout.prop(self, "custom_fps")
        else:
            # Display the current scene FPS (read-only)
            fps = get_scene_fps(context.scene)
            layout.label(text=f"Current Scene FPS: {fps:.3f}")
    
    def execute(self, context):
        scene = context.scene
        if not scene.sequence_editor:
            self.report({'ERROR'}, "No sequence editor found")
            return {'CANCELLED'}
        
        # Determine which FPS to use
        if self.use_scene_fps:
            fps = get_scene_fps(scene)
        else:
            fps = self.custom_fps
        
        # Get selected text strips
        selected_strips = [strip for strip in context.selected_sequences if strip.type == 'TEXT']
        
        if not selected_strips:
            self.report({'ERROR'}, "No text strips selected")
            return {'CANCELLED'}
        
        # Sort strips by start frame
        selected_strips.sort(key=lambda strip: strip.frame_start)
        
        # Write SRT file
        try:
            with open(self.filepath, 'w', encoding='utf-8') as file:
                for i, strip in enumerate(selected_strips, 1):
                    # Calculate start and end times in SRT format
                    start_sec = (strip.frame_start - 1) / fps
                    end_sec = strip.frame_final_end / fps
                    
                    start_time = format_srt_time(start_sec)
                    end_time = format_srt_time(end_sec)
                    
                    # Write subtitle entry
                    file.write(f"{i}\n")
                    file.write(f"{start_time} --> {end_time}\n")
                    file.write(f"{strip.text}\n\n")
            
            # Get file name
            filename = os.path.basename(self.filepath)
            self.report({'INFO'}, f"Success. From [{filename}] there are [{len(selected_strips)}] subtitles exported using FPS: [{fps:.3f}]")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error exporting SRT: {str(e)}")
            return {'CANCELLED'}

# VSE Menu
class SEQUENCER_MT_srt_menu(Menu):
    bl_label = "SRT"
    bl_idname = "SEQUENCER_MT_srt_menu"
    
    def draw(self, context):
        layout = self.layout
        layout.operator(SEQUENCER_OT_ImportSRT.bl_idname, text="Import SRT")
        layout.operator(SEQUENCER_OT_ExportSRT.bl_idname, text="Export SRT")

# Side Panel
class SEQUENCER_PT_srt_panel(Panel):
    bl_label = "SRT Subtitles"
    bl_idname = "SEQUENCER_PT_srt_panel"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'SRT'  # This will create a new tab in the sidebar
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Import/Export Buttons
        row = layout.row()
        row.operator(SEQUENCER_OT_ImportSRT.bl_idname, text="Import SRT", icon='IMPORT')
        row = layout.row()
        row.operator(SEQUENCER_OT_ExportSRT.bl_idname, text="Export SRT", icon='EXPORT')
        
        layout.separator()
        
        # Template Settings
        box = layout.box()
        box.label(text="Subtitle Settings")
        
        # Template name input
        box.prop(scene.srt_props, "template_name")
        
        # text template selection - standard Blender UI pattern
        # scene.srt_proprs (the PropertyGroup)
        # "template_strip" (the StringProperty to store the name of the selected text template)
        # scene.sequence_editor (search_data object)
        # "sequences_all" (the list of all text strips in the scene)
        # text (the label of the UI element)
        row = box.row(align=True)
        row.prop_search(scene.srt_props, "template_strip", scene.sequence_editor, "sequences_all", text="Text Template")
        # Show the "Set Selected" button if a single text strip is selected
        if context.selected_sequences and len(context.selected_sequences) == 1 and context.selected_sequences[0].type == 'TEXT':
            op = row.operator("sequencer.set_template_strip", text="", icon='EYEDROPPER')
            op.strip_name = context.selected_sequences[0].name

# Operator for text template in SRT Side Panel to set the selected strip as template
class SEQUENCER_OT_set_template_strip(Operator):
    bl_idname = "sequencer.set_template_strip"
    bl_label = "Set Selected as Template"
    bl_description = "Use the currently selected text strip as template"
    
    strip_name: StringProperty()
    
    def execute(self, context):
        context.scene.srt_props.template_strip = self.strip_name
        return {'FINISHED'}

# Menu integration function
def draw_srt_menu(self, context):
    layout = self.layout
    layout.menu(SEQUENCER_MT_srt_menu.bl_idname)

def register():

    # 1. Register property group

    # SRTProperties is a property group class used to define custom properties. These properties can store the configuration information of the plugin.
    # For example, the template name and the selection of the text template.
    bpy.utils.register_class(SRTProperties)
    bpy.types.Scene.srt_props = PointerProperty(type=SRTProperties)
    
    # 2. Register classes
    
    # SEQUENCER_OT_ImportSRT is an operator class. It's used to import subtitles from an SRT file into Blender's Video Sequence Editor.
    # Users can specify parameters such as the start frame, subtitle channel, and whether to use the scene's frame rate.
    bpy.utils.register_class(SEQUENCER_OT_ImportSRT)
    
    # SEQUENCER_OT_ExportSRT is an operator class. It's used to export selected text strips as an SRT file.
    # Users can choose whether to use the scene's frame rate for conversion.
    bpy.utils.register_class(SEQUENCER_OT_ExportSRT)
    
    # SEQUENCER_MT_srt_menu is a menu class. It's used to create a menu named "SRT" in the Video Sequence Editor's menu.
    # This menu provides options to import and export SRT files.
    bpy.utils.register_class(SEQUENCER_MT_srt_menu)
    
    # SEQUENCER_PT_srt_panel is a panel class. It's used to create a panel named "SRT Subtitles" in the sidebar of the Video Sequence Editor.
    # The panel contains import/export buttons and template settings.
    bpy.utils.register_class(SEQUENCER_PT_srt_panel)
    
    # SEQUENCER_OT_set_template_strip is an operator class. It's used to set the currently selected text strip as a template.
    # Users can quickly set the text template by clicking a button.
    bpy.utils.register_class(SEQUENCER_OT_set_template_strip)
    
    # 3. Add to VSE menu
    # Append the draw_srt_menu function to the Video Sequence Editor's menu to display the "SRT" menu.
    bpy.types.SEQUENCER_MT_editor_menus.append(draw_srt_menu)

def unregister():
    # Remove from VSE menu
    bpy.types.SEQUENCER_MT_editor_menus.remove(draw_srt_menu)
    
    # Unregister classes
    bpy.utils.unregister_class(SEQUENCER_OT_set_template_strip)
    bpy.utils.unregister_class(SEQUENCER_PT_srt_panel)
    bpy.utils.unregister_class(SEQUENCER_MT_srt_menu)
    bpy.utils.unregister_class(SEQUENCER_OT_ExportSRT)
    bpy.utils.unregister_class(SEQUENCER_OT_ImportSRT)
    
    # Unregister property group
    bpy.utils.unregister_class(SRTProperties)
    del bpy.types.Scene.srt_props

if __name__ == "__main__":
    register()    