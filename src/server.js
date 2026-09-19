import http from 'node:http';
import { createApp } from './app.js';

const port = Number.parseInt(process.env.PORT ?? '3000', 10);
const app = createApp();
const server = http.createServer(app.handler);
let shuttingDown = false;

app.refreshResults().catch((error) => {
  console.error('Initial GarminHRR60 refresh failed:', error);
});
app.startAutoRefresh();

server.listen(port, () => {
  console.log(`GarminHRR60 dashboard listening on http://localhost:${port}`);
});

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.once(signal, async () => {
    if (shuttingDown) {
      return;
    }

    shuttingDown = true;
    app.stopAutoRefresh();
    process.exitCode = 0;

    try {
      await new Promise((resolve, reject) => {
        server.close((error) => {
          if (error) {
            reject(error);
            return;
          }

          resolve();
        });
      });
      await app.waitForRefresh();
    } catch (error) {
      process.exitCode = 1;
      console.error('GarminHRR60 shutdown failed:', error);
    }
  });
}
