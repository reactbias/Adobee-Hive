import { test, expect } from '@playwright/test';

test.describe('Adobee Hive Recruitment Portal E2E Tests', () => {
  test('User can browse job postings, filter candidates with AI co-pilot, and inspect telemetry dossier', async ({ page }) => {
    // 1. Visit root dashboard
    await page.goto('/');

    // Verify brand header & KPIs
    await expect(page.locator('text=adobee hive').first()).toBeVisible();
    await expect(page.locator('text=Active Job Postings & Requisitions')).toBeVisible();
    // 2. Click "View Applicant Pool & AI Filter" if roles exist
    const viewPoolBtn = page.locator('text=View Applicant Pool & AI Filter').first();
    if (await viewPoolBtn.isVisible()) {
      await viewPoolBtn.click();

      // 3. Candidate Search / Workbench View
      await expect(page.locator('text=Hive AI Co-pilot')).toBeVisible();
      await expect(page.locator('text=Filtered Pool')).toBeVisible();

      // 4. Test clicking quick prompt in AI co-pilot if visible
      const priorFoundersPrompt = page.locator('button:has-text("+ Prior Founders")');
      if (await priorFoundersPrompt.isVisible()) {
        await priorFoundersPrompt.click();
      }

      // 5. Inspect candidate dossier if available
      const inspectDossierLink = page.locator('text=Inspect full dossier').first();
      if (await inspectDossierLink.isVisible()) {
        await inspectDossierLink.click();
        await expect(page.locator('text=Backend Requisition Telemetry & Scorecards')).toBeVisible();
        await expect(page.locator('text=Automated AI Code Repository Analysis')).toBeVisible();
      }
    }

    // 7. Navigate to Analytics & Pipelines
    await page.locator('text=Analytics & Pipelines').click();
    await expect(page.locator('text=Talent Pipeline Intelligence')).toBeVisible();
    await expect(page.locator('text=Requisition Funnel Progression')).toBeVisible();
    await expect(page.locator('text=Candidate Sourcing Channels')).toBeVisible();
  });
});
