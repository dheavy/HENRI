import { useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import * as THREE from 'three';
import type { Country } from '../api/client';

// Approximate centroids for ICRC delegation countries (lat, lon)
const CENTROIDS: Record<string, [number, number]> = {
  AF: [33, 65], AZ: [40, 50], BD: [24, 90], BF: [12, -2], BI: [-3, 30],
  BR: [-10, -55], CF: [7, 21], CM: [6, 12], CO: [4, -72], CD: [0, 25],
  CI: [8, -5], DJ: [12, 43], ER: [15, 39], ET: [9, 38], FJ: [-18, 178],
  FR: [46, 2], GE: [42, 44], GH: [8, -2], GN: [11, -10], GT: [16, -90],
  HN: [15, -87], IL: [31, 35], IN: [21, 79], IQ: [33, 44], IR: [32, 53],
  JO: [31, 36], KE: [0, 38], KG: [41, 75], KW: [29, 48], LB: [34, 36],
  LK: [7, 81], LR: [6, -10], ML: [17, -4], MM: [22, 96], MX: [23, -102],
  MZ: [-19, 35], NE: [18, 8], NG: [10, 8], PK: [30, 70], PE: [-10, -76],
  PH: [12, 122], PS: [32, 35], RU: [60, 100], RW: [-2, 30], SD: [15, 30],
  SL: [9, -12], SN: [14, -14], SO: [6, 46], SS: [7, 30], SY: [35, 38],
  TD: [15, 19], TH: [15, 101], TJ: [39, 71], TZ: [-6, 35], UA: [49, 32],
  UG: [1, 32], US: [38, -97], UZ: [41, 65], VE: [8, -66], YE: [15, 48],
  ZM: [-15, 28], ZW: [-20, 30], GB: [54, -2], MY: [4, 102],
};

const TIER_COLORS: Record<string, number> = {
  high: 0xD83C3B,
  medium: 0xD88A6C,
  low: 0xE5C46B,
  minimal: 0xA8C97A,
};

function latLonToVec3(lat: number, lon: number, radius: number): THREE.Vector3 {
  const phi = (90 - lat) * (Math.PI / 180);
  const theta = (lon + 180) * (Math.PI / 180);
  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta),
  );
}

function tierFromScore(score: number): string {
  if (score >= 70) return 'high';
  if (score >= 50) return 'medium';
  if (score >= 25) return 'low';
  return 'minimal';
}

interface Props {
  countries: Country[];
}

export default function MiniGlobe({ countries }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const hovered = useRef(false);

  const init = useCallback((el: HTMLDivElement) => {
    const w = el.clientWidth;
    const h = el.clientHeight;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 100);
    camera.position.set(0, 1.2, 3.2);
    camera.lookAt(0, 0, 0);

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setSize(w, h);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    el.appendChild(renderer.domElement);

    // Globe wireframe (subtle)
    const wireGeo = new THREE.SphereGeometry(1, 32, 32);
    const wireMat = new THREE.MeshBasicMaterial({
      color: 0x3A3D44,
      wireframe: true,
      transparent: true,
      opacity: 0.08,
    });
    const wire = new THREE.Mesh(wireGeo, wireMat);
    scene.add(wire);

    // Delegation dots
    const group = new THREE.Group();
    const dotGeo = new THREE.SphereGeometry(0.025, 8, 8);

    for (const c of countries) {
      const coords = CENTROIDS[c.iso2.toUpperCase()];
      if (!coords) continue;
      const tier = tierFromScore(c.risk_score);
      const color = TIER_COLORS[tier] ?? 0x5C5F66;
      const mat = new THREE.MeshBasicMaterial({ color });
      const dot = new THREE.Mesh(dotGeo, mat);
      const pos = latLonToVec3(coords[0], coords[1], 1.02);
      dot.position.copy(pos);
      dot.userData = { iso2: c.iso2, name: c.name, score: c.risk_score };
      group.add(dot);
    }
    scene.add(group);

    // Animation
    let animId = 0;
    const clock = new THREE.Clock();

    const animate = () => {
      animId = requestAnimationFrame(animate);
      if (!hovered.current) {
        const t = clock.getElapsedTime();
        group.rotation.y = t * 0.1; // ~1 rev per 60s
        wire.rotation.y = t * 0.1;
      }
      renderer.render(scene, camera);
    };
    animate();

    // Hover pause
    const onEnter = () => { hovered.current = true; };
    const onLeave = () => { hovered.current = false; };
    el.addEventListener('mouseenter', onEnter);
    el.addEventListener('mouseleave', onLeave);

    // Resize
    const onResize = () => {
      const nw = el.clientWidth;
      const nh = el.clientHeight;
      camera.aspect = nw / nh;
      camera.updateProjectionMatrix();
      renderer.setSize(nw, nh);
    };
    const ro = new ResizeObserver(onResize);
    ro.observe(el);

    // Cleanup
    return () => {
      cancelAnimationFrame(animId);
      ro.disconnect();
      el.removeEventListener('mouseenter', onEnter);
      el.removeEventListener('mouseleave', onLeave);
      renderer.dispose();
      el.removeChild(renderer.domElement);
    };
  }, [countries]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || countries.length === 0) return;
    return init(el);
  }, [countries, init]);

  return (
    <div
      ref={containerRef}
      className="w-full h-full cursor-pointer"
      onClick={() => navigate('/globe')}
      title="Click to open full globe view"
    />
  );
}
