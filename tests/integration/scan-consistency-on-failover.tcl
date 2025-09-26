start_server {tags {"scan-consistency-on-failover external:skip"}} {

    set fixed_seed "aabbccddeeff"
    set shared_overrides [list appendonly no save "" db-hash-seed $fixed_seed activedefrag no hz 1]

    start_server [list overrides $shared_overrides] {
        set primary_host [srv 0 host]
        set primary_port [srv 0 port]

        start_server [list overrides $shared_overrides] {
            set primary [srv -1 client]
            set replica [srv 0 client]

            $primary flushall
            $replica replicaof $primary_host $primary_port
            wait_for_sync $replica

            set n 50
            for {set i 0} {$i < $n} {incr i} {
                $primary set "k:$i" x
            }

            wait_for_condition 200 50 {
                [$replica dbsize] == [$primary dbsize]
            } else {
                fail "replica did not catch up dbsize (primary=[$primary dbsize], replica=[$replica dbsize])"
            }

            set cursor {{0} {}}
            while {1} {
                set cursor_next [$primary scan [lindex $cursor 0]]
                assert_equal $cursor_next [$replica scan [lindex $cursor 0]]
                if {[lindex $cursor_next 0] eq "0"} break
                set cursor $cursor_next
            }
        }
    }
}