import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { StatusAlert } from "@/components/common/StatusAlert";
import { StatusBadge } from "@/components/common/StatusBadge";
import { DsSection } from "@/components/design-system/DsSection";
import { DS } from "@/constants/testIds";

const ROWS = [
  ["AV-SAMPLE-0001", "[Vendor A]", "processing", "gold"],
  ["AV-SAMPLE-0002", "[Vendor B]", "shipped", "indigo"],
  ["AV-SAMPLE-0003", "[Vendor C]", "delivered", "success"],
  ["AV-SAMPLE-0004", "[Vendor D]", "cancelled", "danger"],
];

export const AlertSection = () => (
  <DsSection id="alerts" title="Alerts & badges" description="Tone maps to meaning, never colour alone — each alert carries an icon and title.">
    <div className="grid gap-4 md:grid-cols-2">
      <StatusAlert tone="info" title="Information" testId="ds-alert-info">Your store review usually takes a few business days.</StatusAlert>
      <StatusAlert tone="success" title="Success" testId="ds-alert-success">Changes saved.</StatusAlert>
      <StatusAlert tone="warning" title="Warning" testId="ds-alert-warning">Low stock on 2 variants.</StatusAlert>
      <StatusAlert tone="error" title="Error" testId="ds-alert-error">Payment could not be processed.</StatusAlert>
    </div>
    <div className="mt-6 flex flex-wrap gap-2">
      {["neutral", "clay", "gold", "indigo", "success", "danger"].map((t) => <StatusBadge key={t} tone={t} testId={`ds-badge-${t}`}>{t}</StatusBadge>)}
    </div>
  </DsSection>
);

export const TableSection = () => (
  <DsSection id="tables" title="Tables" description="Sample data only. Horizontal scroll on small screens.">
    <div className="overflow-x-auto rounded-2xl border border-av-line bg-white">
      <Table data-testid={DS.table}>
        <TableHeader>
          <TableRow className="bg-av-sand hover:bg-av-sand">
            <TableHead>Order</TableHead><TableHead>Vendor</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Total</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {ROWS.map(([id, vendor, status, tone]) => (
            <TableRow key={id}>
              <TableCell className="font-mono text-xs">{id}</TableCell>
              <TableCell>{vendor}</TableCell>
              <TableCell><StatusBadge tone={tone}>{status}</StatusBadge></TableCell>
              <TableCell className="text-right">$0.00</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  </DsSection>
);

export const ModalSection = () => (
  <DsSection id="modal" title="Modal" description="Focus is trapped inside; Esc or Close returns focus to the trigger.">
    <Dialog>
      <DialogTrigger asChild><Button variant="indigo" data-testid={DS.modalTrigger}>Open modal</Button></DialogTrigger>
      <DialogContent className="rounded-2xl bg-av-linen" data-testid="ds-modal">
        <DialogHeader>
          <DialogTitle className="font-serif text-2xl">Confirm action</DialogTitle>
          <DialogDescription>This is a demo dialog. Confirming does nothing.</DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2">
          <DialogClose asChild><Button variant="outline" data-testid={DS.modalClose}>Close</Button></DialogClose>
          <DialogClose asChild><Button data-testid={DS.modalConfirm}>Confirm</Button></DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </DsSection>
);
