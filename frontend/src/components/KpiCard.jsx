import React from 'react';
import '../../styles/global.css';

export default function KpiCard({label,value,delta}){
  return (
    <div className="kpi card">
      <div className="label" style={{color:'var(--text-low)'}}>{label}</div>
      <div className="value">{value}</div>
      <div className="delta" style={{color:delta>0?'var(--success)':'var(--danger)'}}>{delta>0?`▲ ${delta}%`:`▼ ${Math.abs(delta)}%`}</div>
    </div>
  );
}
