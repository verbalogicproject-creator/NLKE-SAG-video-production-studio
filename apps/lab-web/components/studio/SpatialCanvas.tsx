'use client';

import { Html, Line, OrbitControls } from '@react-three/drei';
import { Canvas } from '@react-three/fiber';
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';

type SpatialEntity = {
  id: string;
  kind: string;
  label: string;
  semantic_layer: string;
  position: { x: number; y: number; z: number };
  bounds: { width: number; height: number; depth: number };
};

type SpatialEdge = {
  id: string;
  source: string;
  target: string;
  relationship_kind: string;
};

function Scene({
  entities, edges, selectedId, onSelect,
}: {
  entities: SpatialEntity[];
  edges: SpatialEdge[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const positions = useMemo(
    () => new Map(entities.map((entity) => [entity.id, [entity.position.x, -entity.position.y, entity.position.z / 4] as const])),
    [entities],
  );

  return <>
    <color attach="background" args={['#0e1013']} />
    <ambientLight intensity={1.25} />
    <directionalLight position={[25, 35, 40]} intensity={1.8} color="#dce9ef" />
    {edges.map((edge) => {
      const source = positions.get(edge.source);
      const target = positions.get(edge.target);
      if (!source || !target) return null;
      return <Line
        key={edge.id}
        points={[source, target]}
        color="#3f4851"
        transparent
        opacity={edge.relationship_kind === 'contains' ? 0.34 : 0.7}
        lineWidth={0.7}
      />;
    })}
    {entities.map((entity) => {
      const position = positions.get(entity.id)!;
      const selected = entity.id === selectedId;
      const width = Math.max(1.4, Math.min(12, entity.bounds.width / 2));
      return <group key={entity.id} position={position}>
        <mesh
          onClick={(event) => { event.stopPropagation(); onSelect(entity.id); }}
          scale={[width, 1.25, entity.kind === 'semantic_layer' ? 0.4 : 0.8]}
        >
          <boxGeometry />
          <meshStandardMaterial
            color={selected ? '#5bb9e3' : entity.kind === 'semantic_layer' ? '#273039' : '#20272d'}
            emissive={selected ? '#16394a' : '#0e1013'}
            roughness={0.78}
            metalness={0.08}
          />
        </mesh>
        <Html center distanceFactor={26} occlude={false} style={{ pointerEvents: 'none' }}>
          <span className={`spatial-canvas-label ${selected ? 'selected' : ''}`}>{entity.label}</span>
        </Html>
      </group>;
    })}
    <OrbitControls makeDefault enableDamping={false} minDistance={12} maxDistance={180} />
  </>;
}

function SpatialCanvasComponent({
  entities, edges, selectedId, onSelect,
}: {
  entities: SpatialEntity[];
  edges: SpatialEdge[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const [contextLost, setContextLost] = useState(false);
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const onContextLost = useCallback((event: Event) => {
    event.preventDefault();
    setContextLost(true);
  }, []);
  useEffect(() => () => {
    canvas.current?.removeEventListener('webglcontextlost', onContextLost);
  }, [onContextLost]);
  if (contextLost) return <div className="studio-spatial-fallback" role="alert">
    <strong>3D context lost</strong><span>Use the semantic hierarchy to continue.</span>
  </div>;
  return <Canvas
    className="studio-spatial-canvas"
    camera={{ position: [36, 34, 72], fov: 48, near: 0.1, far: 1000 }}
    dpr={[1, 1.5]}
    frameloop="demand"
    gl={{ antialias: true, powerPreference: 'high-performance' }}
    onCreated={({ gl }) => {
      canvas.current?.removeEventListener('webglcontextlost', onContextLost);
      canvas.current = gl.domElement;
      canvas.current.addEventListener('webglcontextlost', onContextLost, { once: true });
    }}
  >
    <Scene entities={entities} edges={edges} selectedId={selectedId} onSelect={onSelect} />
  </Canvas>;
}

export default memo(SpatialCanvasComponent);
