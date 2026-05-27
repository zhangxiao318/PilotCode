/*
 * PilotCode Remote Agent - Pure C, zero external dependencies.
 * Build: gcc -O2 -s -static -o agent agent.c
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <unistd.h>
#include <sys/wait.h>
#include <errno.h>

#define MAX_LINE  (256 * 1024)   /* 256KB max JSON line */
#define MAX_FILE  (16 * 1024 * 1024) /* 16MB max file read */

/* ------------------------------------------------------------------ */
/* Minimal JSON scanner                                               */
/* ------------------------------------------------------------------ */

static void skip_ws(const char *s, size_t *i) {
    while (s[*i] && isspace((unsigned char)s[*i])) (*i)++;
}

static int parse_string(const char *s, size_t *i, char *out, size_t outsz) {
    size_t j = 0;
    if (s[*i] != '"') return -1;
    (*i)++;
    while (s[*i] && s[*i] != '"') {
        if (s[*i] == '\\' && s[*i + 1]) {
            (*i)++;
            switch (s[*i]) {
                case 'n': if (j < outsz - 1) out[j++] = '\n'; break;
                case 't': if (j < outsz - 1) out[j++] = '\t'; break;
                case 'r': if (j < outsz - 1) out[j++] = '\r'; break;
                case '\\': case '"': case '/':
                    if (j < outsz - 1) out[j++] = s[*i]; break;
                default: if (j < outsz - 1) out[j++] = s[*i]; break;
            }
            (*i)++;
        } else {
            if (j < outsz - 1) out[j++] = s[*i];
            (*i)++;
        }
    }
    if (s[*i] == '"') (*i)++;
    out[j] = '\0';
    return 0;
}

static void skip_value(const char *s, size_t *i) {
    skip_ws(s, i);
    if (s[*i] == '"') {
        char tmp[8];
        parse_string(s, i, tmp, sizeof(tmp));
    } else if (s[*i] == '{') {
        int depth = 1;
        (*i)++;
        while (s[*i] && depth > 0) {
            if (s[*i] == '"') {
                char tmp[8];
                parse_string(s, i, tmp, sizeof(tmp));
            } else {
                if (s[*i] == '{') depth++;
                else if (s[*i] == '}') depth--;
                (*i)++;
            }
        }
    } else if (s[*i] == '[') {
        int depth = 1;
        (*i)++;
        while (s[*i] && depth > 0) {
            if (s[*i] == '"') {
                char tmp[8];
                parse_string(s, i, tmp, sizeof(tmp));
            } else {
                if (s[*i] == '[') depth++;
                else if (s[*i] == ']') depth--;
                (*i)++;
            }
        }
    } else {
        while (s[*i] && s[*i] != ',' && s[*i] != '}' && s[*i] != ']') (*i)++;
    }
}

static int json_get_string(const char *json, const char *key, char *out, size_t outsz) {
    size_t i = 0;
    skip_ws(json, &i);
    if (json[i] != '{') return -1;
    i++;
    while (json[i]) {
        skip_ws(json, &i);
        if (json[i] == '}') break;
        char k[256];
        if (parse_string(json, &i, k, sizeof(k)) != 0) return -1;
        skip_ws(json, &i);
        if (json[i] == ':') i++;
        skip_ws(json, &i);
        if (strcmp(k, key) == 0) {
            return parse_string(json, &i, out, outsz);
        }
        skip_value(json, &i);
        skip_ws(json, &i);
        if (json[i] == ',') i++;
    }
    return -1;
}

static long json_get_int(const char *json, const char *key) {
    size_t i = 0;
    skip_ws(json, &i);
    if (json[i] != '{') return -1;
    i++;
    while (json[i]) {
        skip_ws(json, &i);
        if (json[i] == '}') break;
        char k[256];
        if (parse_string(json, &i, k, sizeof(k)) != 0) return -1;
        skip_ws(json, &i);
        if (json[i] == ':') i++;
        skip_ws(json, &i);
        if (strcmp(k, key) == 0) {
            if (!isdigit((unsigned char)json[i]) && json[i] != '-') return -1;
            char *end;
            long v = strtol(json + i, &end, 10);
            return v;
        }
        skip_value(json, &i);
        skip_ws(json, &i);
        if (json[i] == ',') i++;
    }
    return -1;
}

/* Extract the raw substring of a key's value (for params object) */
static int json_get_value_raw(const char *json, const char *key, char *out, size_t outsz) {
    size_t i = 0, start;
    skip_ws(json, &i);
    if (json[i] != '{') return -1;
    i++;
    while (json[i]) {
        skip_ws(json, &i);
        if (json[i] == '}') break;
        char k[256];
        if (parse_string(json, &i, k, sizeof(k)) != 0) return -1;
        skip_ws(json, &i);
        if (json[i] == ':') i++;
        skip_ws(json, &i);
        if (strcmp(k, key) == 0) {
            start = i;
            skip_value(json, &i);
            size_t len = i - start;
            if (len >= outsz) len = outsz - 1;
            memcpy(out, json + start, len);
            out[len] = '\0';
            return 0;
        }
        skip_value(json, &i);
        skip_ws(json, &i);
        if (json[i] == ',') i++;
    }
    return -1;
}

/* ------------------------------------------------------------------ */
/* JSON string escaping for output                                     */
/* ------------------------------------------------------------------ */

static void json_escape(const char *src, char *dst, size_t dstsz) {
    size_t j = 0;
    dst[j++] = '"';
    for (size_t i = 0; src[i] && j + 6 < dstsz; i++) {
        unsigned char c = src[i];
        if (c == '"') { dst[j++] = '\\'; dst[j++] = '"'; }
        else if (c == '\\') { dst[j++] = '\\'; dst[j++] = '\\'; }
        else if (c == '\n') { dst[j++] = '\\'; dst[j++] = 'n'; }
        else if (c == '\r') { dst[j++] = '\\'; dst[j++] = 'r'; }
        else if (c == '\t') { dst[j++] = '\\'; dst[j++] = 't'; }
        else if (c < 0x20) {
            snprintf(dst + j, dstsz - j, "\\u%04x", c);
            j += 6;
        } else {
            dst[j++] = c;
        }
    }
    dst[j++] = '"';
    dst[j] = '\0';
}

/* ------------------------------------------------------------------ */
/* Response helpers                                                    */
/* ------------------------------------------------------------------ */

static void send_ok(long id, const char *result_json) {
    printf("{\"id\":%ld,\"result\":%s}\n", id, result_json);
    fflush(stdout);
}

static void send_ok_str(long id, const char *key, const char *value) {
    char esc[65536];
    json_escape(value, esc, sizeof(esc));
    printf("{\"id\":%ld,\"result\":{\"%s\":%s}}\n", id, key, esc);
    fflush(stdout);
}

static void send_err(long id, const char *msg) {
    char esc[4096];
    json_escape(msg, esc, sizeof(esc));
    printf("{\"id\":%ld,\"error\":%s}\n", id, esc);
    fflush(stdout);
}

/* ------------------------------------------------------------------ */
/* Handlers                                                            */
/* ------------------------------------------------------------------ */

static void handle_read_file(long id, const char *params_json) {
    char path[2048];
    if (json_get_string(params_json, "path", path, sizeof(path)) != 0) {
        send_err(id, "missing path"); return;
    }

    FILE *f = fopen(path, "rb");
    if (!f) { send_err(id, strerror(errno)); return; }

    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    if (sz < 0 || sz > MAX_FILE) { fclose(f); send_err(id, "file too large"); return; }
    fseek(f, 0, SEEK_SET);

    char *buf = malloc((size_t)sz + 1);
    if (!buf) { fclose(f); send_err(id, "out of memory"); return; }

    size_t n = fread(buf, 1, (size_t)sz, f);
    fclose(f);
    buf[n] = '\0';

    /* Simple heuristic: if binary, refuse */
    for (size_t i = 0; i < n && i < 4096; i++) {
        if (buf[i] == '\0') { free(buf); send_err(id, "binary file"); return; }
    }

    send_ok_str(id, "content", buf);
    free(buf);
}

static void handle_write_file(long id, const char *params_json) {
    char path[2048];
    char content[65536];
    if (json_get_string(params_json, "path", path, sizeof(path)) != 0) {
        send_err(id, "missing path"); return;
    }
    if (json_get_string(params_json, "content", content, sizeof(content)) != 0) {
        send_err(id, "missing content"); return;
    }

    FILE *f = fopen(path, "wb");
    if (!f) { send_err(id, strerror(errno)); return; }

    size_t len = strlen(content);
    if (fwrite(content, 1, len, f) != len) {
        fclose(f); send_err(id, strerror(errno)); return;
    }
    fclose(f);
    send_ok(id, "null");
}

static void handle_exec(long id, const char *params_json) {
    char command[8192];
    char cwd[2048] = {0};
    if (json_get_string(params_json, "command", command, sizeof(command)) != 0) {
        send_err(id, "missing command"); return;
    }
    json_get_string(params_json, "cwd", cwd, sizeof(cwd)); /* optional */

    /* Build a shell command that also captures exit code */
    char script[16384];
    snprintf(script, sizeof(script),
        "{ %s ; printf \"\\n__EXIT_CODE__=$?\\n\" ; } 2>&1",
        command);

    FILE *fp = popen(script, "r");
    if (!fp) { send_err(id, strerror(errno)); return; }

    /* Change cwd for the shell if requested */
    if (cwd[0]) {
        /* popen runs sh -c, cwd doesn't affect it easily.
         * For a robust agent, use fork/exec directly. Here we prefix cd.
         */
        pclose(fp);
        char script2[16384];
        snprintf(script2, sizeof(script2),
            "{ cd %s && %s ; printf \"\\n__EXIT_CODE__=$?\\n\" ; } 2>&1",
            cwd, command);
        fp = popen(script2, "r");
        if (!fp) { send_err(id, strerror(errno)); return; }
    }

    char out[65536] = {0};
    size_t outlen = 0;
    char line[4096];
    int exit_code = -1;

    while (fgets(line, sizeof(line), fp)) {
        size_t ll = strlen(line);
        if (ll >= 14 && strncmp(line, "__EXIT_CODE__=", 14) == 0) {
            exit_code = atoi(line + 14);
            break;
        }
        if (outlen + ll < sizeof(out) - 1) {
            memcpy(out + outlen, line, ll);
            outlen += ll;
            out[outlen] = '\0';
        }
    }
    pclose(fp);

    char esc_out[131072];
    char esc_err[8] = "\"\"";
    json_escape(out, esc_out, sizeof(esc_out));
    printf("{\"id\":%ld,\"result\":{\"stdout\":%s,\"stderr\":%s,\"code\":%d}}\n",
           id, esc_out, esc_err, exit_code);
    fflush(stdout);
}

static void handle_ping(long id) {
    send_ok_str(id, "result", "pong");
}

/* ------------------------------------------------------------------ */
/* Main loop                                                           */
/* ------------------------------------------------------------------ */

int main(void) {
    char *line = NULL;
    size_t len = 0;
    ssize_t n;

    while ((n = getline(&line, &len, stdin)) != -1) {
        if (n > 0 && line[n - 1] == '\n') line[n - 1] = '\0';
        if (line[0] == '\0') continue;

        long id = json_get_int(line, "id");
        char method[64];
        if (json_get_string(line, "method", method, sizeof(method)) != 0) {
            send_err(id >= 0 ? id : 0, "missing method");
            continue;
        }

        char params[65536];
        if (json_get_value_raw(line, "params", params, sizeof(params)) != 0) {
            params[0] = '{'; params[1] = '}'; params[2] = '\0';
        }

        if (strcmp(method, "ping") == 0) handle_ping(id);
        else if (strcmp(method, "read_file") == 0) handle_read_file(id, params);
        else if (strcmp(method, "write_file") == 0) handle_write_file(id, params);
        else if (strcmp(method, "exec") == 0) handle_exec(id, params);
        else send_err(id, "unknown method");
    }

    free(line);
    return 0;
}
