import { PDFDocument, StandardFonts, rgb } from 'pdf-lib';
import { writeFileSync, mkdirSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const outPath = join(__dirname, '..', 'public', 'sample.pdf');

async function main() {
  const doc = await PDFDocument.create();
  const font = await doc.embedFont(StandardFonts.Helvetica);
  const bold = await doc.embedFont(StandardFonts.HelveticaBold);

  const page1 = doc.addPage([612, 792]);
  page1.drawText('PDF Field Editor — Sample Agreement', {
    x: 50,
    y: 720,
    size: 18,
    font: bold,
    color: rgb(0.1, 0.1, 0.2),
  });
  page1.drawText('Page 1 of 2 — place text, date, signature, and comment fields here.', {
    x: 50,
    y: 690,
    size: 11,
    font,
  });
  page1.drawText('Shipper Name: ______________________________________', {
    x: 50,
    y: 640,
    size: 12,
    font,
  });
  page1.drawText('Effective Date: ________________', {
    x: 50,
    y: 600,
    size: 12,
    font,
  });
  page1.drawText('Authorized Signature: ______________________________', {
    x: 50,
    y: 200,
    size: 12,
    font,
  });

  const page2 = doc.addPage([612, 792]);
  page2.drawText('Sample Agreement — Page 2', {
    x: 50,
    y: 720,
    size: 16,
    font: bold,
  });
  page2.drawText('Additional terms and multi-page placement verification.', {
    x: 50,
    y: 690,
    size: 11,
    font,
  });
  page2.drawText('Witness Signature: ________________________________', {
    x: 50,
    y: 400,
    size: 12,
    font,
  });

  const bytes = await doc.save();
  mkdirSync(dirname(outPath), { recursive: true });
  writeFileSync(outPath, bytes);
  console.log(`Wrote ${outPath} (${bytes.length} bytes)`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
