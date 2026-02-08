import type { PermissionLevel } from '../types';

export interface PermissionOption {
  value: PermissionLevel | 'inherit';
  label: string;
}

const BASE_OPTIONS: PermissionOption[] = [
  { value: 'read', label: 'Readable' },
  { value: 'write', label: 'Writable' },
  { value: 'none', label: 'No access' },
  { value: 'inherit', label: 'Inherit' },
];

const FALLBACK_LABEL: Record<PermissionLevel, string> = {
  read: 'Readable',
  write: 'Writable',
  none: 'No access',
};

export function buildPermissionOptions(current: PermissionLevel): PermissionOption[] {
  const seen = new Set<string>();
  const options: PermissionOption[] = [];
  const currentOption = BASE_OPTIONS.find(option => option.value === current) || {
    value: current,
    label: FALLBACK_LABEL[current],
  };

  for (const option of [currentOption, ...BASE_OPTIONS]) {
    if (seen.has(option.value)) continue;
    options.push(option);
    seen.add(option.value);
  }
  return options;
}
