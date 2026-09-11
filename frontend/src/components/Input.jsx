import React from 'react';
import '../../styles/global.css';

export default function Input({label,...props}){
  return (
    <label className="form-field">
      {label && <span className="form-label">{label}</span>}
      <input className="input" {...props} />
    </label>
  );
}
