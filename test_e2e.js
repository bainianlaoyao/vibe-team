import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Ensure evidence directory exists
const evidenceDir = path.join(__dirname, 'evidence');
if (!fs.existsSync(evidenceDir)) {
  fs.mkdirSync(evidenceDir, { recursive: true });
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function runTests() {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await context.newPage();

  try {
    console.log('Starting E2E Tests...');

    // Test 1: WebSocket connection
    console.log('\n=== Test 1: WebSocket Connection ===');
    await page.goto('http://localhost:5173/chat', { waitUntil: 'networkidle' });
    await sleep(3000); // Wait for page load and connection

    // Take initial screenshot
    await page.screenshot({ path: path.join(evidenceDir, 'test_websocket_connected.png') });
    console.log('✓ Test 1: Screenshot saved');

    // Log page content for debugging
    const pageTitle = await page.title();
    console.log('Page title:', pageTitle);

    const pageContent = await page.textContent('body').then(t => t?.slice(0, 500) || '');
    console.log('Page content preview:', pageContent);

    await sleep(2000);

    // Test 2: Send normal message
    console.log('\n=== Test 2: Normal Message ===');
    const inputBox = page.locator('textarea').first();
    await inputBox.click();
    await inputBox.fill('Hello, Claude!');
    await inputBox.press('Enter');
    await sleep(3000); // Wait for response

    // Wait for streaming response
    await sleep(5000);

    await page.screenshot({ path: path.join(evidenceDir, 'test_normal_message.png') });
    console.log('✓ Test 2: Screenshot saved');

    await sleep(2000);

    // Test 3: Tool call display
    console.log('\n=== Test 3: Tool Call Display ===');
    await page.locator('textarea').first().click();
    await page.locator('textarea').first().fill('List all files in the current directory');
    await page.locator('textarea').first().press('Enter');
    await sleep(8000); // Wait for tool execution

    await page.screenshot({ path: path.join(evidenceDir, 'test_tool_call.png') });
    console.log('✓ Test 3: Screenshot saved');

    await sleep(2000);

    // Test 4: Thinking block display
    console.log('\n=== Test 4: Thinking Block Display ===');
    await page.locator('textarea').first().click();
    await page.locator('textarea').first().fill('Explain quantum computing in simple terms');
    await page.locator('textarea').first().press('Enter');
    await sleep(5000); // Wait for response with thinking

    // Try to find and click thinking accordion
    const thinkingAccordion = page.locator('text=/thinking/i').first();
    const thinkingVisible = await thinkingAccordion.isVisible().catch(() => false);
    if (thinkingVisible) {
      await thinkingAccordion.click();
    }
    await sleep(2000);

    await page.screenshot({ path: path.join(evidenceDir, 'test_thinking.png') });
    console.log('✓ Test 4: Screenshot saved');

    await sleep(2000);

    // Test 5: UserQuestion flow
    console.log('\n=== Test 5: UserQuestion Flow ===');
    await page.locator('textarea').first().click();
    await page.locator('textarea').first().fill('What is your name? Use request_input tool.');
    await page.locator('textarea').first().press('Enter');
    await sleep(5000); // Wait for input request

    // Screenshot 1: Input request card
    await page.screenshot({ path: path.join(evidenceDir, 'test_input_request_1.png') });
    console.log('✓ Test 5.1: Input request card screenshot saved');

    // Fill and submit user answer
    await page.locator('textarea').first().click();
    await page.locator('textarea').first().fill('My name is Atlas');
    await sleep(1000);

    const submitButton = page.locator('button:has-text("Submit")')
      .or(page.locator('button:has-text("Send")'))
      .first();
    await submitButton.click();
    await sleep(3000);

    // Screenshot 2: User response
    await page.screenshot({ path: path.join(evidenceDir, 'test_input_request_2.png') });
    console.log('✓ Test 5.2: User response screenshot saved');

    await sleep(4000); // Wait for Claude's response

    // Screenshot 3: Claude continues
    await page.screenshot({ path: path.join(evidenceDir, 'test_input_request_3.png') });
    console.log('✓ Test 5.3: Claude continues screenshot saved');

    await sleep(2000);

    // Test 6: Interrupt functionality
    console.log('\n=== Test 6: Interrupt Functionality ===');
    await page.locator('textarea').first().click();
    await page.locator('textarea').first().fill('Write a very long essay about artificial intelligence');
    await page.locator('textarea').first().press('Enter');
    await sleep(2000); // Wait for streaming to start

    // Click stop button
    const stopButton = page.locator('button:has-text("Stop")').first();
    const stopButtonVisible = await stopButton.isVisible().catch(() => false);

    if (stopButtonVisible) {
      await stopButton.click();
      console.log('✓ Stop button clicked');
    } else {
      console.log('⚠ Stop button not visible');
    }

    await sleep(3000);

    await page.screenshot({ path: path.join(evidenceDir, 'test_interrupt.png') });
    console.log('✓ Test 6: Screenshot saved');

    await sleep(2000);

    // Test 7: Reconnection (skip in automated test - requires manual restart)
    console.log('\n=== Test 7: Reconnection (SKIPPED - requires manual backend restart) ===');

    // Test 8: Error handling
    console.log('\n=== Test 8: Error Handling (SKIPPED - requires manual API key test) ===');

    console.log('\n✅ All tests completed!');
    console.log(`Screenshots saved to: ${evidenceDir}`);

  } catch (error) {
    console.error('Error during tests:', error);
    throw error;
  } finally {
    await browser.close();
  }
}

runTests().catch(console.error);
