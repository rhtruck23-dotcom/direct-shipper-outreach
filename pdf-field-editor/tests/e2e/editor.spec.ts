import { test, expect } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const samplePdf = path.resolve(__dirname, '../../public/sample.pdf');

test.describe('PDF Field Editor', () => {
  test('upload, place each field type, move/resize, signature, download', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByTestId('app-root')).toBeVisible();

    await page.getByTestId('file-input').setInputFiles(samplePdf);
    await expect(page.getByTestId('pdf-viewer')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId('page-canvas-0')).toBeVisible();

    const canvas = page.getByTestId('page-canvas-0').locator('div').first();
    const box = await canvas.boundingBox();
    expect(box).toBeTruthy();
    if (!box) return;

    // Place text via click
    await page.getByTestId('tool-text').click();
    await page.mouse.click(box.x + 80, box.y + 80);
    await expect(page.locator('[data-field-type="text"]')).toHaveCount(1);

    // Place date via drag
    await page.getByTestId('tool-date').click();
    await page.mouse.move(box.x + 80, box.y + 140);
    await page.mouse.down();
    await page.mouse.move(box.x + 200, box.y + 170);
    await page.mouse.up();
    await expect(page.locator('[data-field-type="date"]')).toHaveCount(1);

    // Place signature
    await page.getByTestId('tool-signature').click();
    await page.mouse.click(box.x + 100, box.y + 500);
    await expect(page.locator('[data-field-type="signature"]')).toHaveCount(1);

    // Place comment
    await page.getByTestId('tool-comment').click();
    await page.mouse.click(box.x + 350, box.y + 200);
    await expect(page.locator('[data-field-type="comment"]')).toHaveCount(1);

    // Select text field, edit name in property panel
    await page.locator('[data-field-type="text"]').click();
    await expect(page.getByTestId('property-panel')).toBeVisible();
    await page.getByTestId('prop-name').fill('ShipperName');

    // Move selected field with react-rnd (drag)
    const textField = page.locator('[data-field-type="text"]');
    const textBox = await textField.boundingBox();
    expect(textBox).toBeTruthy();
    if (textBox) {
      await page.mouse.move(textBox.x + textBox.width / 2, textBox.y + textBox.height / 2);
      await page.mouse.down();
      await page.mouse.move(textBox.x + 40, textBox.y + 30);
      await page.mouse.up();
    }

    // Resize via bottom-right handle (react-rnd creates handles)
    const afterMove = await textField.boundingBox();
    if (afterMove) {
      await page.mouse.move(afterMove.x + afterMove.width - 2, afterMove.y + afterMove.height - 2);
      await page.mouse.down();
      await page.mouse.move(afterMove.x + afterMove.width + 40, afterMove.y + afterMove.height + 10);
      await page.mouse.up();
    }

    // Signature: open modal, draw via SignaturePad API, apply
    await page.locator('[data-field-type="signature"]').dblclick();
    await expect(page.getByTestId('signature-modal')).toBeVisible();
    await page.getByTestId('signature-canvas').waitFor({ state: 'visible' });
    await page.waitForFunction(
      () =>
        document.querySelector('[data-testid="signature-canvas"]')?.getAttribute('data-pad-ready') ===
        'true',
    );
    await page.evaluate(() => {
      const canvas = document.querySelector(
        '[data-testid="signature-canvas"]',
      ) as HTMLCanvasElement & {
        __signaturePad?: {
          fromData: (points: unknown) => void;
          isEmpty: () => boolean;
        };
      };
      const pad = canvas.__signaturePad;
      if (!pad) throw new Error('SignaturePad not attached');
      pad.fromData([
        {
          color: 'rgb(16, 24, 40)',
          points: [
            { time: 1, x: 40, y: 100 },
            { time: 2, x: 120, y: 60 },
            { time: 3, x: 220, y: 110 },
            { time: 4, x: 340, y: 70 },
          ],
        },
      ]);
      if (pad.isEmpty()) throw new Error('Signature still empty after fromData');
    });
    await page.getByTestId('signature-apply').click();
    await expect(page.getByTestId('signature-modal')).toBeHidden({ timeout: 10_000 });

    // Comment text via property panel
    await page.locator('[data-field-type="comment"]').click();
    await page.getByTestId('prop-comment-text').fill('Looks good');

    // Download
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByTestId('download-button').click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/fillable\.pdf$/i);
    const downloadPath = await download.path();
    expect(downloadPath).toBeTruthy();
  });
});
