import axios from "axios";

export const api = axios.create({
  baseURL: `${process.env.REACT_APP_BACKEND_URL}/api/v1`,
  timeout: 15000,
});

export const getErrorMessage = (err) =>
  err?.response?.data?.error?.message || "Something went wrong. Please try again.";
