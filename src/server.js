import http from 'node:http';
import { createApp } from './app.js';

const port = Number.parseInt(process.env.PORT ?? '3000', 10);
const app = createApp();
const server = http.createServer(app.handler);

app.refreshResults().catch(() => {});
app.startAutoRefresh();

server.listen(port, () => {
  console.log(`GarminHRR60 dashboard listening on http://localhost:${port}`);
});

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    app.stopAutoRefresh();
    server.close(() => process.exit(0));
  });
}
