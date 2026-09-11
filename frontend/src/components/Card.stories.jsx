import React from 'react';
import Card from './Card';

export default { title: 'Components/Card', component: Card };
export const Default = () => <Card><h3>Card title</h3><p style={{color:'var(--text-low)'}}>Card content goes here.</p></Card>;
