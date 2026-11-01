import React from 'react';
import { Department } from '../../types';

interface DepartmentTabsProps {
  selectedDepartment: Department;
  onSelectDepartment: (dept: Department) => void;
}

export const DepartmentTabs: React.FC<DepartmentTabsProps> = ({
  selectedDepartment,
  onSelectDepartment,
}) => {
  const departments: { id: Department; label: string }[] = [
    { id: 'All Departments', label: 'All Departments' },
    { id: 'Engineering', label: 'Engineering' },
    { id: 'Product & Design', label: 'Product & Design' },
    { id: 'Sales & Marketing', label: 'Sales & Marketing' },
    { id: 'Data & AI', label: 'Data & AI' },
  ];

  return (
    <div className="relative z-10 flex flex-wrap items-center gap-2 pt-2">
      {departments.map((dept) => {
        const isSelected = selectedDepartment === dept.id;
        return (
          <button
            key={dept.id}
            onClick={() => onSelectDepartment(dept.id)}
            className={`font-sans text-xs font-semibold px-3.5 py-1.5 rounded-lg transition-all ${
              isSelected
                ? 'bg-primary text-black shadow-sm shadow-amber-500/20'
                : 'bg-surface-container-high text-on-surface-variant hover:text-on-surface hover:bg-surface-bright'
            }`}
          >
            {dept.label}
          </button>
        );
      })}
    </div>
  );
};
