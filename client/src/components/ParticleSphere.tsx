import { useEffect, useRef } from 'react';
import * as THREE from 'three';

interface ParticleSphereProps {
  className?: string;
}

export function ParticleSphere({ className = '' }: ParticleSphereProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const frameRef = useRef<number>(0);

  useEffect(() => {
    if (!containerRef.current) return;

    const container = containerRef.current;
    const width = container.clientWidth;
    const height = container.clientHeight;

    // Scene setup
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 1000);
    camera.position.z = 2.5;

    // Renderer
    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      powerPreference: 'high-performance'
    });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0); // Transparent background
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Create particle sphere geometry
    const particleCount = 2500;
    const positions = new Float32Array(particleCount * 3);
    const colors = new Float32Array(particleCount * 3);
    const sizes = new Float32Array(particleCount);

    // Grayscale color variations - Darker for Light Mode
    const baseColor = new THREE.Color(0x000000); // Pure Black
    const darkColor = new THREE.Color(0x18181b); // Zinc-950
    const lightColor = new THREE.Color(0x27272a); // Zinc-800

    for (let i = 0; i < particleCount; i++) {
      // Fibonacci sphere distribution
      const phi = Math.acos(1 - 2 * (i + 0.5) / particleCount);
      const theta = Math.PI * (1 + Math.sqrt(5)) * (i + 0.5);

      const radius = 1;
      positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
      positions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
      positions[i * 3 + 2] = radius * Math.cos(phi);

      colors[i * 3] = 0.1; // Dark gray
      colors[i * 3 + 1] = 0.1;
      colors[i * 3 + 2] = 0.1;

      // Sizes
      sizes[i] = 4.0;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1));

    // Custom shader material - HIGH VISIBILITY DEBUG MODE
    const material = new THREE.ShaderMaterial({
      uniforms: {
        time: { value: 0 },
        pixelRatio: { value: renderer.getPixelRatio() }
      },
      vertexShader: `
        attribute float size;
        attribute vec3 color;
        varying vec3 vColor;
        uniform float time;
        uniform float pixelRatio;

        void main() {
          vColor = color;
          vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
          
          // Ensure meaningful size
          gl_PointSize = size * (300.0 / -mvPosition.z) * pixelRatio;
          gl_Position = projectionMatrix * mvPosition;
        }
      `,
      fragmentShader: `
        varying vec3 vColor;

        void main() {
          // Sharp circular edge
          vec2 coord = gl_PointCoord - vec2(0.5);
          if(length(coord) > 0.5) discard;

          // SOLID BLACK for maximum visibility test
          gl_FragColor = vec4(0.0, 0.0, 0.0, 1.0);
        }
      `,
      transparent: true,
      depthWrite: false,
      blending: THREE.NormalBlending
    });

    const particles = new THREE.Points(geometry, material);
    scene.add(particles);

    // Add wireframe sphere - High Visibility
    const wireGeometry = new THREE.SphereGeometry(1.02, 32, 32);
    const wireMaterial = new THREE.MeshBasicMaterial({
      color: 0x000000,
      wireframe: true,
      transparent: true,
      opacity: 0.3
    });
    const wireSphere = new THREE.Mesh(wireGeometry, wireMaterial);
    scene.add(wireSphere);

    // Add glow ring around equator
    const ringGeometry = new THREE.RingGeometry(1.15, 1.18, 64);
    const ringMaterial = new THREE.MeshBasicMaterial({
      color: 0x000000,
      transparent: true,
      opacity: 0.3,
      side: THREE.DoubleSide
    });
    const ring = new THREE.Mesh(ringGeometry, ringMaterial);
    ring.rotation.x = Math.PI / 2;
    scene.add(ring);

    // Animation
    let time = 0;
    const animate = () => {
      frameRef.current = requestAnimationFrame(animate);
      time += 0.01;

      // Slow rotation
      particles.rotation.y += 0.001;
      particles.rotation.x = Math.sin(time * 0.2) * 0.1;

      wireSphere.rotation.y = particles.rotation.y;
      wireSphere.rotation.x = particles.rotation.x;

      ring.rotation.z += 0.0005;

      material.uniforms.time.value = time;

      renderer.render(scene, camera);
    };

    animate();

    // Handle resize
    const handleResize = () => {
      if (!containerRef.current) return;
      const newWidth = containerRef.current.clientWidth;
      const newHeight = containerRef.current.clientHeight;

      camera.aspect = newWidth / newHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(newWidth, newHeight);
    };

    window.addEventListener('resize', handleResize);

    // Cleanup
    return () => {
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(frameRef.current);

      if (rendererRef.current && containerRef.current) {
        containerRef.current.removeChild(rendererRef.current.domElement);
        rendererRef.current.dispose();
      }

      geometry.dispose();
      material.dispose();
      wireGeometry.dispose();
      wireMaterial.dispose();
      ringGeometry.dispose();
      ringMaterial.dispose();
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className={`relative ${className}`}
      style={{ minHeight: '300px' }}
    >
      {/* Focal point indicator */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none z-10">
        <div className="relative">
          {/* Crosshair */}
          <div className="absolute w-8 h-px bg-zinc-400/50 -left-4 top-1/2" />
          <div className="absolute h-8 w-px bg-zinc-400/50 left-1/2 -top-4" />
          {/* Center dot */}
          <div className="w-2 h-2 rounded-full bg-zinc-900 shadow-[0_0_10px_rgba(24,24,27,0.5)]" />
          {/* Corner brackets */}
          <div className="absolute -top-6 -left-6 w-3 h-3 border-t border-l border-zinc-400/40" />
          <div className="absolute -top-6 -right-6 w-3 h-3 border-t border-r border-zinc-400/40" />
          <div className="absolute -bottom-6 -left-6 w-3 h-3 border-b border-l border-zinc-400/40" />
          <div className="absolute -bottom-6 -right-6 w-3 h-3 border-b border-r border-zinc-400/40" />
        </div>
      </div>

      {/* Glow effect behind sphere */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="w-[60%] h-[60%] rounded-full bg-zinc-400/10 blur-[60px]" />
      </div>
    </div>
  );
}

export default ParticleSphere;
