import { expect, test } from '@playwright/test';

test('dashboard and key routes render', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('BeeBeeBrain MVP')).toBeVisible();
  await expect(page.getByText('Recent Updates')).toBeVisible();

  await page.goto('/inbox');
  await expect(page.getByRole('heading', { name: 'Inbox' })).toBeVisible();

  await page.goto('/chat');
  await expect(page.getByText('Workspace Chat')).toBeVisible();

  await page.goto('/agents/kanban');
  await expect(page.locator('body')).toContainText(
    /Loading tasks|Failed to load tasks|REQUEST_FAILED|In progress|No tasks/,
  );
});
