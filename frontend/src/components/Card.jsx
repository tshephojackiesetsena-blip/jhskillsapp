import React from 'react';
import '../../styles/global.css';

export default function Card({children,style}){
  return <div className="card" style={style}>{children}</div>;
}
