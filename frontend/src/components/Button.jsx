import React from 'react';
import '../../styles/global.css';

export default function Button({children,variant='primary',...props}){
  const cls = `btn ${variant==='primary' ? 'btn-primary' : 'btn-secondary'}`;
  return <button className={cls} {...props}>{children}</button>
}
