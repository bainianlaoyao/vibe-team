import { describe, expect, it } from 'vitest';
import { buildPermissionOptions } from '../../src/utils/filePermissionOptions';

describe('buildPermissionOptions', () => {
  it('keeps options unique when current permission already exists in defaults', () => {
    const options = buildPermissionOptions('read');
    const values = options.map(item => item.value);
    expect(new Set(values).size).toBe(values.length);
    expect(values.filter(value => value === 'read')).toHaveLength(1);
  });

  it('keeps current permission as the first option', () => {
    const options = buildPermissionOptions('write');
    expect(options[0]?.value).toBe('write');
  });
});
