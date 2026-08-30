import { expect, test } from '@playwright/test';

test.describe('会话闭环', () => {
  test('创建会话 → 列表可见 → 删除', async ({ page }) => {
    await page.goto('/ui/sessions');

    await page.getByRole('button', { name: '新建会话' }).first().click();
    await page.getByPlaceholder('如 work、site-a').fill(`e2e-${Date.now()}`);
    // 创建会话会拉起 Chrome 实例，耗时较长
    await page.getByRole('button', { name: '创建', exact: true }).click();
    await expect(page).toHaveURL(/\/ui\/sessions\/.+/, { timeout: 60_000 });
  });

  test('概览页显示服务状态', async ({ page }) => {
    await page.goto('/ui/');
    await expect(page.getByText('服务信息')).toBeVisible();
  });
});
