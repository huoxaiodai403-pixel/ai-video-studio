// Adapted from trustfuture/simon-skills (MIT), assets/BrandStamp.jsx.
// Uses the bundled Noto font instead of the upstream macOS-only SignPainter.
import React from 'react';

export function BrandStamp({brand, dark = true, top = 38, right = 66}) {
  return <div style={{position: 'absolute', top, right, zIndex: 20, display: 'flex', gap: 13,
    alignItems: 'center', color: dark ? '#f8faf6' : '#19221e', maxWidth: 460}}>
    <svg width="30" height="30" viewBox="0 0 40 40"><path d="M20 0 L24 15 L40 20 L24 25 L20 40 L16 25 L0 20 L16 15 Z" fill={brand.accent}/></svg>
    <div style={{fontSize: brand.signature.length > 15 ? 21 : 28, fontWeight: 700, borderBottom: `4px solid ${brand.accent}`,
      padding: '0 3px 8px', letterSpacing: 1, lineHeight: 1.3}}>{brand.signature}</div>
  </div>;
}
