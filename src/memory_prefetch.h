#ifndef MEMORY_PREFETCH_H
#define MEMORY_PREFETCH_H

struct client;

void prefetchCommandsBatchInit(void);
void processClientsCommandsBatch(void);
int addCommandToBatchAndProcessIfFull(struct client *c);
void removeClientFromPendingCommandsBatch(struct client *c);
int onMaxBatchSizeChange(const char **err);

void prefetchKeys(struct client *c, int first, int step, int count);

#endif /* MEMORY_PREFETCH_H */
