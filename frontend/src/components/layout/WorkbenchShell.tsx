import React, { useState } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";
import LeftPane from "./LeftPane";
import CenterPane from "./CenterPane";
import RightPane from "./RightPane";
import BottomDock from "./BottomDock";

export default function WorkbenchShell() {
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-4 py-2 flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">KuzuWiki-OSINT</h1>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500">Graph-Compiled Expert Intelligence</span>
        </div>
      </header>

      <Group orientation="horizontal" className="flex-1 overflow-hidden">
        <Panel defaultSize={20} minSize={15}>
          <LeftPane
            selectedEntityId={selectedEntityId}
            onSelectEntity={setSelectedEntityId}
          />
        </Panel>
        <Separator />
        <Panel defaultSize={45} minSize={30}>
          <CenterPane entityId={selectedEntityId} />
        </Panel>
        <Separator />
        <Panel defaultSize={25} minSize={20}>
          <RightPane entityId={selectedEntityId} />
        </Panel>
      </Group>

      <Group orientation="vertical" className="h-64 shrink-0">
        <Panel defaultSize={70} minSize={30}>
          <BottomDock />
        </Panel>
      </Group>
    </div>
  );
}
