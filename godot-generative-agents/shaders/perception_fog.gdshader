shader_type canvas_item;

// Perception fog for the campus replay: when you Track an agent, the world OUTSIDE
// their perception radius is dimmed under a translucent grey cover, leaving a clear
// circle around them (the same vision_r the sim uses to decide what they perceive).
//
// Driven by penn_replay.gd, which fills these uniforms each frame in the overlay
// rect's own pixel space (a full-screen ColorRect on a CanvasLayer):
//   center    -- the tracked agent's on-screen position
//   radius    -- fully-clear radius around them, in screen pixels
//   feather   -- width of the soft fade band just outside the circle
//   rect_size -- the overlay's size, so UV maps back to pixels
// Inside `radius` the cover is fully transparent; past `radius + feather` it is the
// full grey; smoothstep blends the edge so the boundary isn't a hard ring.
uniform vec2 center = vec2(0.0);
uniform float radius = 200.0;
uniform float feather = 60.0;
uniform vec4 cover_color : source_color = vec4(0.18, 0.19, 0.22, 0.72);
uniform vec2 rect_size = vec2(1.0, 1.0);

void fragment() {
	float d = distance(UV * rect_size, center);
	float a = smoothstep(radius, radius + feather, d);
	COLOR = vec4(cover_color.rgb, cover_color.a * a);
}
