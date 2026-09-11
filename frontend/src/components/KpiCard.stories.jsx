import React from 'react';
import KpiCard from './KpiCard';

export default { title: 'Components/KPI Card', component: KpiCard };
export const Example = () => <KpiCard label="Learners" value="1,248" delta={4.2} />;
