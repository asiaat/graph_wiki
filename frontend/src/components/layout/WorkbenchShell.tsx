import React from "react";
import { ResizablePanelGroup, ResizablePanel, Separator } from "react-resizable-panels";
import LeftPane from "./LeftPane";
import CenterPane from "./CenterPane";
import RightPane from "./RightPane";
import BottomDock from "./BottomDock";

export default function WorkbenchShell() {
  return (
    <div className="flex flex-col h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-4 py-2 flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">KuzuWiki-OSINT</h1>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500">Graph-Compiled Expert Intelligence</span>
        </div>
      </header>

      <ResizablePanelGroup direction="horizontal" className="flex-1 overflow-hidden">
        <ResizablePanel defaultSize={20} minSize={15}>
          <LeftPane />
        </ResizablePanel>
        <Separator />
        <ResizablePanel defaultSize={45} minSize={30}>
          <CenterPane />
        </ResizablePanel>
        <Separator />
        <ResizablePanel defaultSize={25} minSize={20}>
          <RightPane />
        </ResizablePanel>
      </ResizablePanelGroup>

      <ResizablePanelGroup direction="vertical">
        <Separator />
        <ResizablePanel defaultSize={20} minSize={10}>
          <BottomDock />
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}