# =============================================================================
# Makefile — marvell-crypto-bench C shared library
#
# Targets:
#   make all    — Build libcryptobench.so (default)
#   make clean  — Remove all build artefacts
#   make asan   — Build with AddressSanitizer enabled
#
# Output: libcryptobench.so  (placed in this directory)
# =============================================================================

CC      = gcc
CFLAGS  = -O2 -march=native -Wall -Wextra -fPIC -std=c99
LDFLAGS = -shared -lm
ASAN_FLAGS = -fsanitize=address -fno-omit-frame-pointer -g

SRCS    = aes256.c sha256.c bench_api.c
OBJS    = $(SRCS:.c=.o)
TARGET  = libcryptobench.so

.PHONY: all clean asan

# ---- Default target ----------------------------------------------------------
all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(LDFLAGS) -o $@ $^

%.o: %.c
	$(CC) $(CFLAGS) -c -o $@ $<

# ---- AddressSanitizer build ---------------------------------------------------
asan: CFLAGS += $(ASAN_FLAGS)
asan: LDFLAGS += $(ASAN_FLAGS)
asan: clean $(TARGET)

# ---- Clean -------------------------------------------------------------------
clean:
	rm -f $(OBJS) $(TARGET)

# ---- Explicit dependencies ---------------------------------------------------
aes256.o:    aes256.c aes256.h
sha256.o:    sha256.c sha256.h
bench_api.o: bench_api.c bench_api.h aes256.h sha256.h
