import ky from 'ky';

const api = ky.create({
  prefixUrl: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

export default api;
