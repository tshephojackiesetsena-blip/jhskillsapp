import React from 'react';
import '../../styles/global.css';

export default function Sidebar({items=["Dashboard","Projects","Learners","Finance","Reports"],collapsed=false}){
  return (
    <aside className="sidebar" aria-label="Main navigation">
      <div style={{fontWeight:700,marginBottom:12}}>JH Skills</div>
      <nav>
        {items.map(i=> <div key={i} style={{padding:'8px 6px',borderRadius:6,marginBottom:6}}>{i}</div>)}
      </nav>
    </aside>
  );
}
