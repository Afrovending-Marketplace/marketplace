import { useEffect, useState } from "react";
import { StatusAlert } from "@/components/common/StatusAlert";
import { api } from "@/lib/api";

export const useOrdersStatus = () => {
  const [s, setS] = useState({ accepting: true, message: "" });
  useEffect(() => {
    api.get("/orders-status").then((r) => setS(r.data)).catch(() => {});
  }, []);
  return s;
};

export const OrdersClosedNotice = ({ status, testId = "orders-closed-notice" }) =>
  status.accepting ? null : <StatusAlert tone="warning" title="Checkout is closed" testId={testId}>{status.message}</StatusAlert>;
