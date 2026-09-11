import React from 'react';
import Sidebar from './Sidebar';

export default { title: 'Components/Sidebar', component: Sidebar };
export const Default = () => <div style={{display:'flex'}}><Sidebar /><div style={{padding:20}}>Main content</div></div>;
