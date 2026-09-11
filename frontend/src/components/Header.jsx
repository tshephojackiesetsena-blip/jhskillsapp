import React from 'react';
import '../../styles/global.css';

export default function Header(){
  return (
    <header className="header" role="banner">
      <div style={{display:'flex',alignItems:'center',justifyContent:'space-between'}}>
        <div style={{display:'flex',alignItems:'center',gap:12}}>
          <button className="btn btn-secondary">☰</button>
          <div style={{fontWeight:700}}>Executive Dashboard</div>
        </div>
        <div style={{display:'flex',alignItems:'center',gap:8}}>
          <input className="input" placeholder="Search (Ctrl/Cmd K)" style={{width:260}} />
          <button className="btn btn-primary">+ New</button>
        </div>
      </div>
    </header>
  );
}
