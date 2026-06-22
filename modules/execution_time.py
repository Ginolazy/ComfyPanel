## ComfyUI/custom_nodes/ComfyPanel/modules/execution_time.py

import time
import execution
import server
import inspect

CURRENT_START_EXECUTION_DATA = {}

origin_execute = execution.execute

if inspect.iscoroutinefunction(origin_execute):
    async def dev_execute(server, dynprompt, caches, current_item, extra_data, executed, prompt_id,
                          execution_list, pending_subgraph_results, pending_async_nodes, *args, **kwargs):
        unique_id = current_item
        CURRENT_START_EXECUTION_DATA[unique_id] = time.perf_counter()
        result = await origin_execute(server, dynprompt, caches, current_item, extra_data, executed, prompt_id,
                                      execution_list, pending_subgraph_results, pending_async_nodes, *args, **kwargs)
        execution_time = int((time.perf_counter() - CURRENT_START_EXECUTION_DATA[unique_id]) * 1000)
        if server.client_id is not None:
            server.send_sync("ComfyPanel.node.executed", {"node": unique_id, "execution_time": execution_time}, server.client_id)
        return result
else:
    def dev_execute(server, dynprompt, caches, current_item, extra_data, executed, prompt_id,
                    execution_list, pending_subgraph_results, *args, **kwargs):
        unique_id = current_item
        CURRENT_START_EXECUTION_DATA[unique_id] = time.perf_counter()
        result = origin_execute(server, dynprompt, caches, current_item, extra_data, executed, prompt_id,
                                execution_list, pending_subgraph_results, *args, **kwargs)
        execution_time = int((time.perf_counter() - CURRENT_START_EXECUTION_DATA[unique_id]) * 1000)
        if server.client_id is not None:
            server.send_sync("ComfyPanel.node.executed", {"node": unique_id, "execution_time": execution_time}, server.client_id)
        return result

execution.execute = dev_execute
