import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_URL,
  timeout: 0, // No timeout - scraper can take a long time for Cloudflare bypass
  headers: {
    'Content-Type': 'multipart/form-data',
  },
});

export const enrichCompanies = async (file: File): Promise<Blob> => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await api.post('/api/enrich', formData, {
    responseType: 'blob',
  });

  return response.data;
};

export const checkStatus = async (): Promise<any> => {
  const response = await api.get('/api/status');
  return response.data;
};
