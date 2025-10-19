# Copyright [2025] Silvera0218
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import pygame
import moderngl
import numpy as np
import math
from PIL import Image
import os

WINDOW_SIZE = (1280, 720)

BLACK_HOLE_MASS = 0.9
BLACK_HOLE_SPIN = 0.9999
Rs = 2.0 * BLACK_HOLE_MASS

SCHWARZSCHILD_DISK_INNER_RADIUS = 6.0 * BLACK_HOLE_MASS
KERR_DISK_INNER_RADIUS = 6 * BLACK_HOLE_MASS

DISK_OUTER_RADIUS = 12.0 * Rs
DISK_THICKNESS = 0.3

class BlackHole3D:
    def __init__(self, window_size):
        self.width, self.height = window_size
        
        pygame.init()
        
        pygame.display.gl_set_attribute(pygame.GL_FRAMEBUFFER_SRGB_CAPABLE, 1)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
        pygame.display.set_mode(window_size, pygame.OPENGL | pygame.DOUBLEBUF)
        
        self.ctx = moderngl.create_context()
        
        self.program = self.ctx.program(
            vertex_shader=self.get_vertex_shader(),
            fragment_shader=self.get_fragment_shader()
        )
        
        self.distance = 20.0
        self.yaw = math.radians(0)
        self.pitch = math.radians(90)
        pygame.mouse.set_visible(False)
        pygame.event.set_grab(True)

        self.accretion_disk_enabled = True
        self.photon_sphere_enabled = True
        self.kerr_enabled = True

        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            face_names = ['right.png', 'left.png', 'top.png', 'bottom.png', 'back.png', 'front.png']
            image_data_list = []
            
            first_img_path = os.path.join(script_dir, face_names[0])
            first_img = Image.open(first_img_path).convert("RGBA")
            size = first_img.size
            image_data_list.append(first_img.tobytes())
            
            for name in face_names[1:]:
                img_path = os.path.join(script_dir, name)
                img = Image.open(img_path).convert("RGBA")
                image_data_list.append(img.tobytes())
                
            final_image_data = b''.join(image_data_list)
            self.skybox_texture = self.ctx.texture_cube(size, 4, final_image_data)

            self.skybox_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self.skybox_texture.wrap_x = 'clamp_to_edge'
            self.skybox_texture.wrap_y = 'clamp_to_edge'
            self.skybox_texture.wrap_z = 'clamp_to_edge'
            
            self.skybox_texture.use(0)
            self.program['u_skybox'] = 0

        except (FileNotFoundError, ValueError) as e:
            print(f"error for Cubemap texture。")
            print(f"Details: {e}")
            exit()

        self.program['u_resolution'].value = (self.width, self.height)
        self.program['M'].value = BLACK_HOLE_MASS
        self.program['DISK_OUTER_RADIUS'].value = DISK_OUTER_RADIUS
        self.program['DISK_THICKNESS'].value = DISK_THICKNESS

        vertices = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0], dtype='f4')
        vbo = self.ctx.buffer(vertices)
        self.vao = self.ctx.vertex_array(self.program, [(vbo, '2f', 'in_vert')])
        
        self.clock = pygame.time.Clock()

    def get_vertex_shader(self):
        return """
            #version 330 core
            in vec2 in_vert;
            void main() { gl_Position = vec4(in_vert, 0.0, 1.0); }
        """

    def get_fragment_shader(self):
        return """
            #version 330 core
            out vec4 fragColor;

            uniform vec2 u_resolution;
            uniform float M;
            uniform float DISK_INNER_RADIUS;
            uniform float DISK_OUTER_RADIUS;
            uniform float DISK_THICKNESS;
            uniform samplerCube u_skybox;
            uniform vec3 u_camera_pos;
            uniform vec3 u_camera_fwd;
            uniform vec3 u_camera_right;
            uniform vec3 u_camera_up;
            uniform float u_time;
            uniform float u_skybox_rotation; 
            uniform bool u_accretion_disk_enabled; 
            uniform bool u_photon_sphere_enabled;
            uniform bool u_kerr_enabled;
            uniform float a;

            #define Rs (2.0 * M)
            const float PI = 3.1415926535;
            const int MAX_STEPS = 1000;
            const float BASE_DT = 0.06;

            vec3 get_sky_color(vec3 dir) {
                float angle = u_skybox_rotation;
                mat2 rot = mat2(cos(angle), -sin(angle), sin(angle), cos(angle));
                vec3 rotated_dir = dir;
                rotated_dir.xz = rot * rotated_dir.xz;
                return texture(u_skybox, vec3(rotated_dir.x, rotated_dir.y, -rotated_dir.z)).rgb;
            }

            float random(vec2 st) { return fract(sin(dot(st.xy, vec2(12.9898,78.233))) * 43758.5453123); }
            float noise(vec2 st) {
                vec2 i = floor(st); vec2 f = fract(st);
                float a = random(i); float b = random(i + vec2(1.0, 0.0));
                float c = random(i + vec2(0.0, 1.0)); float d = random(i + vec2(1.0, 1.0));
                vec2 u = f * f * (3.0 - 2.0 * f);
                return mix(a, b, u.x) + (c - a) * u.y * (1.0 - u.x) + (d - b) * u.y * u.x;
            }
            float fbm(vec2 st) {
                float value = 0.0; float amplitude = 0.5;
                for (int i = 0; i < 4; i++) {
                    value += amplitude * noise(st); st *= 2.0; amplitude *= 0.5;
                }
                return value;
            }

            vec3 get_disk_color(vec3 pos, vec3 ray_dir) {
                float r_cyl = length(pos.xz);
                if (r_cyl < DISK_INNER_RADIUS || r_cyl > DISK_OUTER_RADIUS) return vec3(0.0);
                float vertical_falloff = 1.0 - smoothstep(0.0, DISK_THICKNESS, abs(pos.y));
                if (vertical_falloff <= 0.0) return vec3(0.0);
                
                float phi = atan(pos.z, pos.x);
                float animated_phi = phi + u_time * 0.2 / (r_cyl * 0.5);
                vec2 base_coord = vec2(cos(animated_phi), sin(animated_phi)) * r_cyl * 0.3;
                
                vec2 warp_coord1 = base_coord + vec2(u_time * 0.1, 0.0);
                vec2 warp_coord2 = base_coord + vec2(0.0, u_time * 0.08);
                vec2 warp_offset = vec2(fbm(warp_coord1), fbm(warp_coord2));
                float noise_val = fbm(base_coord + warp_offset * 0.5);
                
                noise_val = pow(noise_val, 2.5);
                float temp = 1.0 - smoothstep(DISK_INNER_RADIUS, DISK_OUTER_RADIUS, r_cyl);
                temp = pow(temp, 2.0);

                float omega = sqrt(M) / (pow(r_cyl, 1.5) + a * sqrt(M));
                float v_mag = omega * r_cyl;
                vec3 v_dir = normalize(vec3(-pos.z, 0.0, pos.x));
                vec3 disk_velocity = v_mag * v_dir;

                float r = length(pos);
                float r2 = r*r;
                
                float cos2_theta = pos.y * pos.y / r2;
                float r2_sin2_theta = pos.x * pos.x + pos.z * pos.z;
                float rho2 = r2 + a * a * cos2_theta;

                float g_tt = -(1.0 - Rs * r / rho2);
                float g_tphi = -Rs * a * r * r2_sin2_theta / (rho2 * r2);
                float g_phiphi_term = Rs * a * a * r * r2_sin2_theta / (rho2 * r2);
                float g_phiphi = (r2 + a*a + g_phiphi_term) * r2_sin2_theta / r2;
                
                float grav_redshift = sqrt(-g_tt - 2.0*omega*g_tphi - omega*omega*g_phiphi);
                
                float doppler_dot = dot(disk_velocity, ray_dir);
                float doppler_factor = sqrt(1.0 - v_mag*v_mag) / (1.0 - doppler_dot);

                vec3 color_bright = vec3(temp * 1.0, temp * 1.0, temp * 25.0);
                vec3 color_dark = vec3(temp * 1.0, temp * 1.0, temp * 20.0);
                float mix_factor = smoothstep(0.4, 1.6, doppler_factor);
                vec3 base_color = mix(color_dark, color_bright, mix_factor) * noise_val;

                float brightness = pow(doppler_factor, 10.0);
                return base_color * brightness * grav_redshift * vertical_falloff;
            }

            vec3 get_acceleration(vec3 pos, vec3 vel) {
                float r2 = dot(pos, pos);
                if (r2 < 1e-4) return vec3(0.0);
                float r = sqrt(r2);

                vec3 acc_schwarzschild = -M * pos / pow(r, 3.0) * (1.0 + 3.0 * dot(cross(pos, vel), cross(pos, vel)) / (r2));

                if (u_kerr_enabled) {
                    vec3 J = vec3(0, a * M, 0);
                    float r3 = r2 * r;
                    vec3 acc_drag = -(6.0 * M / r3) * cross(vel, J);
                    return acc_schwarzschild + acc_drag;
                }

                return acc_schwarzschild;
            }

            vec3 tonemap_aces(vec3 x) {
                float a = 2.51; float b = 0.03; float c = 2.43;
                float d = 0.59; float e = 0.14;
                return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
            }

            void main() {
                vec2 uv = (2.0 * gl_FragCoord.xy - u_resolution.xy) / u_resolution.y;
                float fov_factor = 0.8; 
                vec3 ray_dir = normalize(u_camera_fwd + (uv.x * u_camera_right + uv.y * u_camera_up) * fov_factor);
                vec3 ray_pos = u_camera_pos;
                vec3 velocity = ray_dir;
                
                bool hit_horizon = false;
                vec3 accumulated_light = vec3(0.0);
                float transparency = 1.0;
                float min_r = 1000.0;

                float horizon_radius = u_kerr_enabled ? M + sqrt(M*M - a*a) : Rs;

                for (int i = 0; i < MAX_STEPS; ++i) {
                    float r = length(ray_pos);
                    min_r = min(min_r, r);

                    if (r < horizon_radius * 1.01) { hit_horizon = true; break; }
                    
                    float DT = BASE_DT;
                    if (r > 1.0) {
                        DT = min(BASE_DT, r * r * 0.005); 
                    }

                    if (u_accretion_disk_enabled) { 
                        float r_disk = length(ray_pos.xz);
                        if (abs(ray_pos.y) < DISK_THICKNESS && r_disk >= DISK_INNER_RADIUS && r_disk < DISK_OUTER_RADIUS) {
                            vec3 step_color = get_disk_color(ray_pos, normalize(velocity)) * DT * 10.0;
                            accumulated_light += step_color * transparency;
                            float opacity = clamp(dot(step_color, vec3(0.333)) * 0.1, 0.0, 1.0);
                            transparency *= (1.0 - opacity);
                            if (transparency < 0.01) { break; }
                        }
                    }
                    
                    vec3 k1_vel = DT * get_acceleration(ray_pos, velocity);
                    vec3 k1_pos = DT * velocity;

                    vec3 k2_vel = DT * get_acceleration(ray_pos + k1_pos * 0.5, velocity + k1_vel * 0.5);
                    vec3 k2_pos = DT * (velocity + k1_vel * 0.5);

                    vec3 k3_vel = DT * get_acceleration(ray_pos + k2_pos * 0.5, velocity + k2_vel * 0.5);
                    vec3 k3_pos = DT * (velocity + k2_vel * 0.5);

                    vec3 k4_vel = DT * get_acceleration(ray_pos + k3_pos, velocity + k3_vel);
                    vec3 k4_pos = DT * (velocity + k3_vel);

                    ray_pos += (k1_pos + 2.0 * k2_pos + 2.0 * k3_pos + k4_pos) / 6.0;
                    velocity += (k1_vel + 2.0 * k2_vel + 2.0 * k3_vel + k4_vel) / 6.0;
                }

                vec3 background_srgb = vec3(0.0);
                if (!hit_horizon) {
                    background_srgb = get_sky_color(normalize(velocity));
                }

                vec3 background_linear = pow(background_srgb, vec3(2.2));
                vec3 tonemapped_disk_linear = tonemap_aces(accumulated_light);
                vec3 final_linear = mix(background_linear, tonemapped_disk_linear, 1.0 - transparency);

                if (!u_kerr_enabled && u_photon_sphere_enabled) {
                    float ring_width = 0.05;
                    float ring_start = Rs + 0.02;
                    float ring_end = ring_start + ring_width;
                    float intensity_up = smoothstep(ring_start, ring_end, min_r);
                    float intensity_down = 1.0 - smoothstep(ring_end, ring_end + ring_width, min_r);
                    float ring_intensity = intensity_up * intensity_down;
                    vec3 ring_color = vec3(1.0, 0.8, 0.4) * 2.0;
                    final_linear += ring_color * ring_intensity * transparency;
                }

                vec3 final_color = pow(final_linear, vec3(1.0/2.2));
                fragColor = vec4(final_color, 1.0);
            }
        """

    def run(self):
            running = True
            while running:
                mouse_dx, mouse_dy = pygame.mouse.get_rel()
                for event in pygame.event.get():
                    if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                        running = False
                    if event.type == pygame.MOUSEWHEEL:
                        self.distance -= event.y * 0.5
                        self.distance = max(2.0 * BLACK_HOLE_MASS * 2.5, min(self.distance, 50.0))
                    
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_SPACE:
                            self.accretion_disk_enabled = not self.accretion_disk_enabled
                        if event.key == pygame.K_p:
                            self.photon_sphere_enabled = not self.photon_sphere_enabled
                        if event.key == pygame.K_s:
                            self.kerr_enabled = not self.kerr_enabled
                            mode = "Kerr (Rotating)" if self.kerr_enabled else "Schwarzschild (Static)"
                            print(f"Switched to {mode} black hole model.")

                if pygame.mouse.get_pressed()[0]:
                    self.yaw += mouse_dx * 0.005
                    self.pitch -= mouse_dy * 0.005
                    self.pitch = max(-math.pi/2 + 0.01, min(self.pitch, math.pi/2 - 0.01))
                
                cam_x = self.distance * math.cos(self.pitch) * math.sin(self.yaw)
                cam_y = self.distance * math.sin(self.pitch)
                cam_z = self.distance * math.cos(self.pitch) * math.cos(self.yaw)
                camera_pos = np.array([cam_x, cam_y, cam_z], dtype='f4')
                
                cam_fwd_x = -math.sin(self.yaw) * math.cos(self.pitch)
                cam_fwd_y = -math.sin(self.pitch)
                cam_fwd_z = -math.cos(self.yaw) * math.cos(self.pitch)
                cam_fwd = np.array([cam_fwd_x, cam_fwd_y, cam_fwd_z], dtype='f4')

                cam_right = np.array([math.cos(self.yaw), 0, -math.sin(self.yaw)], dtype='f4')
                
                cam_up = np.cross(cam_right, cam_fwd)
                
                time_sec = pygame.time.get_ticks() / 1000.0
                self.program['u_time'].value = time_sec
                
                self.program['u_skybox_rotation'].value = time_sec / 20.0
                
                self.program['u_camera_pos'].value = tuple(camera_pos)
                self.program['u_camera_fwd'].value = tuple(cam_fwd)
                self.program['u_camera_right'].value = tuple(cam_right)
                self.program['u_camera_up'].value = tuple(cam_up)
                
                self.program['u_accretion_disk_enabled'].value = self.accretion_disk_enabled
                self.program['u_photon_sphere_enabled'].value = self.photon_sphere_enabled
                
                self.program['u_kerr_enabled'].value = self.kerr_enabled
                spin_a = BLACK_HOLE_SPIN * BLACK_HOLE_MASS if self.kerr_enabled else 0.0
                self.program['a'].value = spin_a

                if self.kerr_enabled:
                    self.program['DISK_INNER_RADIUS'].value = KERR_DISK_INNER_RADIUS
                else:
                    self.program['DISK_INNER_RADIUS'].value = SCHWARZSCHILD_DISK_INNER_RADIUS

                self.ctx.clear(0.0, 0.0, 0.0)
                self.vao.render(moderngl.TRIANGLE_STRIP)
                pygame.display.flip()
                
                self.clock.tick(30)
                pygame.display.set_caption(f"Black Hole Simulation - FPS: {self.clock.get_fps():.2f}")
                
            pygame.quit()

if __name__ == '__main__':
    sim = BlackHole3D(WINDOW_SIZE)
    sim.run()

