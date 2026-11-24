import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TrainingPage } from "./TrainingPage";

const api = vi.hoisted(() => ({
  allDatasetVersions: vi.fn().mockResolvedValue({ data: [{ id: "dataset-1", name: "roads", task: "detect" }] }),
  jobs: vi.fn().mockResolvedValue({ data: [] }),
  createJob: vi.fn(),
  jobAction: vi.fn(),
}));

vi.mock("../lib/api", () => ({ api }));

afterEach(() => cleanup());

describe("TrainingPage", () => {
  it("keeps advanced training parameters collapsed until requested", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <TrainingPage />
      </QueryClientProvider>,
    );

    const advanced = await screen.findByText("高级训练参数");
    expect(advanced.closest("details")).not.toHaveAttribute("open");
  });

  it("explains advanced fields and blocks an empty numeric value before submission", async () => {
    api.allDatasetVersions.mockResolvedValueOnce({ data: [{ id: "dataset-1", name: "roads", task: "detect" }] });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><TrainingPage /></QueryClientProvider>);

    fireEvent.click(await screen.findByText("高级训练参数"));
    expect(screen.getByText("训练开始的学习率；通常保持 0.01，必须大于 0。")).toBeInTheDocument();
    const learningRate = screen.getByLabelText("初始学习率");
    fireEvent.change(learningRate, { target: { value: "" } });
    const submit = screen.getByRole("button", { name: "加入训练队列" });
    await waitFor(() => expect(submit).not.toBeDisabled());
    fireEvent.click(submit);

    expect(await screen.findByText("初始学习率必须填写有效数字。")).toBeInTheDocument();
    await waitFor(() => expect(api.createJob).not.toHaveBeenCalled());
  });

  it("turns a server validation detail into a field-specific message", async () => {
    api.allDatasetVersions.mockResolvedValueOnce({ data: [{ id: "dataset-1", name: "roads", task: "detect" }] });
    api.createJob.mockRejectedValueOnce({
      code: "VALIDATION_ERROR",
      message: "请求参数无效",
      details: [{ loc: ["body", "lr0"], ctx: { gt: 0 } }],
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><TrainingPage /></QueryClientProvider>);

    const submit = await screen.findByRole("button", { name: "加入训练队列" });
    await waitFor(() => expect(submit).not.toBeDisabled());
    fireEvent.click(submit);

    expect(await screen.findByText("初始学习率必须大于 0。")).toBeInTheDocument();
  });

  it("submits the selected RF-DETR Large checkpoint", async () => {
    api.createJob.mockClear();
    api.createJob.mockRejectedValueOnce(new Error("测试请求已收到"));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><TrainingPage /></QueryClientProvider>);

    fireEvent.change(await screen.findByLabelText("训练引擎"), { target: { value: "rfdetr" } });
    expect(screen.queryByText("高级训练参数")).toBeNull();
    fireEvent.change(screen.getByLabelText("模型档位"), { target: { value: "large" } });
    fireEvent.change(screen.getByLabelText("随机种子"), { target: { value: "17" } });
    fireEvent.click(screen.getByRole("button", { name: "加入训练队列" }));
    await waitFor(() => expect(api.createJob).toHaveBeenCalledWith({
      engine: "rfdetr", name: "train-rfdetr-large", task: "detect", datasetVersionId: "dataset-1",
      modelPath: "models/pretrained/rfdetr/rf-detr-large-2026.pth", epochs: 100, batch: 2, lr0: 0.0001, seed: "17",
    }));
  });
});
