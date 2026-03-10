import { useEffect, useRef } from 'react';
import * as THREE from 'three';

interface CityMarker {
  label: string;
  lat: number;
  lon: number;
}

interface ParticleSphereProps {
  className?: string;
  showCityMarkers?: boolean;
  cityMarkers?: CityMarker[];
}

const DEFAULT_CITY_MARKERS: CityMarker[] = [
  // North America
  { label: 'LA', lat: 34.0522, lon: -118.2437 },
  { label: 'SF', lat: 37.7749, lon: -122.4194 },
  { label: 'NY', lat: 40.7128, lon: -74.0060 },
  { label: 'Austin', lat: 30.2672, lon: -97.7431 },
  { label: 'Miami', lat: 25.7617, lon: -80.1918 },
  { label: 'Chicago', lat: 41.8781, lon: -87.6298 },
  { label: 'Toronto', lat: 43.6510, lon: -79.3470 },
  // Latin America
  { label: 'Mexico City', lat: 19.4326, lon: -99.1332 },
  { label: 'Bogota', lat: 4.7110, lon: -74.0721 },
  { label: 'Sao Paulo', lat: -23.5505, lon: -46.6333 },
  { label: 'Buenos Aires', lat: -34.6037, lon: -58.3816 },
  { label: 'Lima', lat: -12.0464, lon: -77.0428 },
  // Europe
  { label: 'London', lat: 51.5074, lon: -0.1278 },
  { label: 'Paris', lat: 48.8566, lon: 2.3522 },
  { label: 'Berlin', lat: 52.5200, lon: 13.4050 },
  // Africa
  { label: 'Lagos', lat: 6.5244, lon: 3.3792 },
  { label: 'Nairobi', lat: -1.2921, lon: 36.8219 },
  { label: 'Cape Town', lat: -33.9249, lon: 18.4241 },
  // Asia / Middle East / Oceania
  { label: 'Dubai', lat: 25.2048, lon: 55.2708 },
  { label: 'Mumbai', lat: 19.0760, lon: 72.8777 },
  { label: 'Tokyo', lat: 35.6762, lon: 139.6503 },
  { label: 'Singapore', lat: 1.3521, lon: 103.8198 },
  { label: 'Seoul', lat: 37.5665, lon: 126.9780 },
  { label: 'Sydney', lat: -33.8688, lon: 151.2093 }
];

const latLonToVector3 = (lat: number, lon: number, radius: number) => {
  const latRad = THREE.MathUtils.degToRad(lat);
  const lonRad = THREE.MathUtils.degToRad(lon);
  const cosLat = Math.cos(latRad);

  return new THREE.Vector3(
    radius * cosLat * Math.sin(lonRad),
    radius * Math.sin(latRad),
    radius * cosLat * Math.cos(lonRad)
  );
};

const createCityLabel = (text: string) => {
  const canvas = document.createElement('canvas');
  canvas.width = 600;
  canvas.height = 160;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  // Add spaces between characters for better readability and style
  const spacedText = text.split('').join(' ').toUpperCase();

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.font = '400 32px "Space Mono", monospace';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = 'rgba(255, 255, 255, 0.95)'; // Solid white
  ctx.shadowColor = 'rgba(0, 0, 0, 0.4)'; // Slightly darker shadow for contrast
  ctx.shadowBlur = 8;
  ctx.fillText(spacedText, canvas.width / 2, canvas.height / 2);

  const texture = new THREE.CanvasTexture(canvas);
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = false;

  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthWrite: false,
    depthTest: true,
    opacity: 0.88
  });

  const sprite = new THREE.Sprite(material);
  sprite.scale.set(0.68, 0.18, 1);
  return { sprite, material, texture };
};

export function ParticleSphere({
  className = '',
  showCityMarkers = false,
  cityMarkers = DEFAULT_CITY_MARKERS
}: ParticleSphereProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const frameRef = useRef<number>(0);

  useEffect(() => {
    if (!containerRef.current) return;

    const container = containerRef.current;

    // Clean up any existing canvas (handles StrictMode double-render)
    const existingCanvas = container.querySelector('canvas');
    if (existingCanvas) {
      container.removeChild(existingCanvas);
    }

    const width = container.clientWidth;
    const height = container.clientHeight;

    // Scene setup
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 1000);
    camera.position.z = 2.5;
    const sphereGroup = new THREE.Group();
    // Pre-rotate to show a dense cluster of cities immediately (Americas + Europe)
    const initialRotationX = THREE.MathUtils.degToRad(15);
    sphereGroup.rotation.y = THREE.MathUtils.degToRad(70);
    sphereGroup.rotation.x = initialRotationX;
    scene.add(sphereGroup);

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
    const isMobile = window.innerWidth < 768;
    const particleCount = isMobile ? 400 : 800; // Drastically reduced from 1000/2500
    const positions = new Float32Array(particleCount * 3);
    const colors = new Float32Array(particleCount * 3);
    const sizes = new Float32Array(particleCount);

    // Grayscale color variations
    const baseColor = new THREE.Color(0x71717a); // zinc-500
    const darkColor = new THREE.Color(0x3f3f46); // zinc-700
    const lightColor = new THREE.Color(0xa1a1aa); // zinc-400

    for (let i = 0; i < particleCount; i++) {
      // Fibonacci sphere distribution for even spacing
      const phi = Math.acos(1 - 2 * (i + 0.5) / particleCount);
      const theta = Math.PI * (1 + Math.sqrt(5)) * (i + 0.5);

      const radius = 1.15;
      positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
      positions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
      positions[i * 3 + 2] = radius * Math.cos(phi);

      // Vary colors slightly
      const colorMix = Math.random();
      const particleColor = colorMix < 0.33
        ? baseColor
        : colorMix < 0.66
          ? darkColor
          : lightColor;

      colors[i * 3] = particleColor.r;
      colors[i * 3 + 1] = particleColor.g;
      colors[i * 3 + 2] = particleColor.b;

      // Vary sizes (make particles smaller to avoid clouding)
      sizes[i] = 1 + Math.random() * 1.5;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1));

    // Custom shader material for glowing particles
    const material = new THREE.ShaderMaterial({
      uniforms: {
        time: { value: 0 },
        pixelRatio: { value: renderer.getPixelRatio() }
      },
      vertexShader: `
        attribute float size;
        attribute vec3 color;
        varying vec3 vColor;
        varying float vAlpha;
        uniform float time;

        void main() {
          vColor = color;

          // Subtle pulsing based on position
          float pulse = sin(time * 0.5 + position.x * 2.0 + position.y * 2.0) * 0.15 + 0.85;
          vAlpha = pulse;

          vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = size * (200.0 / -mvPosition.z) * pixelRatio;
          gl_Position = projectionMatrix * mvPosition;
        }
      `,
      fragmentShader: `
        varying vec3 vColor;
        varying float vAlpha;

        void main() {
          // Sharper circular particle
          float dist = length(gl_PointCoord - vec2(0.5));
          if (dist > 0.5) discard;

          // Less smoothstep bleed to prevent 'cloud' buildup
          float alpha = smoothstep(0.5, 0.35, dist) * vAlpha * 0.8;
          gl_FragColor = vec4(vColor, alpha);
        }
      `,
      transparent: true,
      depthWrite: false,
      blending: THREE.NormalBlending
    });

    const particles = new THREE.Points(geometry, material);
    sphereGroup.add(particles);

    // Add wireframe sphere for structure hint
    const wireGeometry = new THREE.SphereGeometry(1.3, 64, 64);
    const wireMaterial = new THREE.MeshBasicMaterial({
      color: 0x3f3f46, // zinc-700
      wireframe: true,
      transparent: true,
      opacity: 0.2
    });
    const wireSphere = new THREE.Mesh(wireGeometry, wireMaterial);
    sphereGroup.add(wireSphere);

    const markersGroup = new THREE.Group();
    sphereGroup.add(markersGroup);

    type MarkerInstance = {
      normal: THREE.Vector3;
      dotMaterial: THREE.MeshBasicMaterial;
      pulse: THREE.Mesh;
      pulseMaterial: THREE.MeshBasicMaterial;
      labelMaterial?: THREE.SpriteMaterial;
      lineMaterial?: THREE.LineBasicMaterial;
    };

    const markerInstances: MarkerInstance[] = [];
    const markerDotGeometry = new THREE.SphereGeometry(0.016, 16, 16);
    const markerPulseGeometry = new THREE.SphereGeometry(0.028, 14, 14);
    const labelTextures: THREE.CanvasTexture[] = [];
    const labelMaterials: THREE.SpriteMaterial[] = [];
    const lineGeometries: THREE.BufferGeometry[] = [];

    if (showCityMarkers) {
      cityMarkers.forEach((city, index) => {
        const normal = latLonToVector3(city.lat, city.lon, 1.15).normalize();
        const markerPosition = normal.clone().multiplyScalar(1.18);
        const labelAnchor = normal.clone().multiplyScalar(1.45);

        const dotMaterial = new THREE.MeshBasicMaterial({
          color: 0x3f3f46, // zinc-700
          transparent: true,
          opacity: 0.9
        });
        const dot = new THREE.Mesh(markerDotGeometry, dotMaterial);
        dot.position.copy(markerPosition);
        markersGroup.add(dot);

        const pulseMaterial = new THREE.MeshBasicMaterial({
          color: 0xa1a1aa, // zinc-400
          transparent: true,
          opacity: 0.22
        });
        const pulse = new THREE.Mesh(markerPulseGeometry, pulseMaterial);
        pulse.position.copy(markerPosition);
        markersGroup.add(pulse);

        const lineGeometry = new THREE.BufferGeometry().setFromPoints([
          normal.clone().multiplyScalar(1.2),
          normal.clone().multiplyScalar(1.4)
        ]);
        const lineMaterial = new THREE.LineBasicMaterial({
          color: 0xd4d4d8, // zinc-300
          transparent: true,
          opacity: 0.45
        });
        const line = new THREE.Line(lineGeometry, lineMaterial);
        markersGroup.add(line);
        lineGeometries.push(lineGeometry);

        let labelMaterial: THREE.SpriteMaterial | undefined;
        const labelData = createCityLabel(city.label);
        if (labelData) {
          labelData.sprite.position.copy(labelAnchor);
          markersGroup.add(labelData.sprite);
          labelTextures.push(labelData.texture);
          labelMaterials.push(labelData.material);
          labelMaterial = labelData.material;
        }

        markerInstances.push({
          normal: normal.clone(),
          dotMaterial,
          pulse,
          pulseMaterial,
          labelMaterial,
          lineMaterial
        });

        pulse.scale.setScalar(1 + index * 0.02);
      });
    }

    // Visibility observer — skip GPU work when off-screen
    const isVisible = { current: true };
    const observer = new IntersectionObserver(
      ([entry]) => { isVisible.current = entry.isIntersecting; },
      { rootMargin: "200px" }
    );
    observer.observe(container);

    // Animation
    let time = 0;
    const markerNormalWorld = new THREE.Vector3();
    const toCamera = new THREE.Vector3();
    const animate = () => {
      frameRef.current = requestAnimationFrame(animate);
      if (!isVisible.current) return;
      time += 0.01;

      // Slow rotation relative to the initial starting angle
      sphereGroup.rotation.y += 0.001;
      sphereGroup.rotation.x = initialRotationX + Math.sin(time * 0.2) * 0.05;

      markerInstances.forEach((marker, index) => {
        marker.pulse.scale.setScalar(1 + Math.sin(time * 2.2 + index) * 0.18);

        markerNormalWorld
          .copy(marker.normal)
          .applyQuaternion(sphereGroup.quaternion)
          .normalize();
        toCamera.copy(camera.position).normalize();

        const facing = markerNormalWorld.dot(toCamera);
        const visibility = THREE.MathUtils.clamp((facing - 0.05) / 0.35, 0, 1);

        marker.dotMaterial.opacity = 0.22 + visibility * 0.75;
        marker.pulseMaterial.opacity = 0.06 + visibility * 0.24;
        if (marker.labelMaterial) {
          marker.labelMaterial.opacity = visibility;
        }
        if (marker.lineMaterial) {
          marker.lineMaterial.opacity = visibility * 0.55;
        }
      });

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
      observer.disconnect();
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(frameRef.current);

      if (rendererRef.current && containerRef.current) {
        if (containerRef.current.contains(rendererRef.current.domElement)) {
          containerRef.current.removeChild(rendererRef.current.domElement);
        }
        rendererRef.current.dispose();
      }

      geometry.dispose();
      material.dispose();
      wireGeometry.dispose();
      wireMaterial.dispose();
      markerDotGeometry.dispose();
      markerPulseGeometry.dispose();
      markerInstances.forEach((marker) => {
        marker.dotMaterial.dispose();
        marker.pulseMaterial.dispose();
        marker.lineMaterial?.dispose();
      });
      labelMaterials.forEach((material) => material.dispose());
      labelTextures.forEach((texture) => texture.dispose());
      lineGeometries.forEach((lineGeometry) => lineGeometry.dispose());
    };
  }, [showCityMarkers, cityMarkers]);

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
          <div className="absolute w-8 h-px bg-zinc-500/50 -left-4 top-1/2" />
          <div className="absolute h-8 w-px bg-zinc-500/50 left-1/2 -top-4" />
          {/* Center dot */}
          <div className="w-2 h-2 rounded-full bg-zinc-500 shadow-[0_0_10px_rgba(0,0,0,0.1)]" />
          {/* Corner brackets */}
          <div className="absolute -top-6 -left-6 w-3 h-3 border-t border-l border-zinc-500/40" />
          <div className="absolute -top-6 -right-6 w-3 h-3 border-t border-r border-zinc-500/40" />
          <div className="absolute -bottom-6 -left-6 w-3 h-3 border-b border-l border-zinc-500/40" />
          <div className="absolute -bottom-6 -right-6 w-3 h-3 border-b border-r border-zinc-500/40" />
        </div>
      </div>
    </div>
  );
}

export default ParticleSphere;
