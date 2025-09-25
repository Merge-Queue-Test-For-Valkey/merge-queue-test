start_server {tags {"scan-consistency-on-failover external:skip"}} {
    proc full_scan_keys {c prefix} {
        set cur 0
        set out {}
        while {1} {
            # count 1 to make the ordering fully observable
            set res [$c scan $cur count 1]
            set cur  [lindex $res 0]
            set keys [lindex $res 1]
            foreach k $keys {
                if {[string match "${prefix}*" $k]} {
                    lappend out $k
                }
            }
            if {$cur eq "0"} break
        }
        return $out
    }

    set fixed_seed "00112233445566778899aabbccddeeff"
    set shared_overrides [list appendonly no save "" db-hash-seed $fixed_seed activedefrag no hz 1]

    start_server [list overrides $shared_overrides] {
        set primary_host [srv 0 host]
        set primary_port [srv 0 port]

        start_server [list overrides $shared_overrides] {
            set replica_host [srv 0 host]
            set replica_port [srv 0 port]

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

            wait_for_condition 200 50 {
                ![string match {Hash table 1 stats*} [$primary debug htstats 9]] &&
                ![string match {Hash table 1 stats*} [$replica debug htstats 9]] &&
                [dict get [$primary memory stats] db.dict.rehashing.count] == 0 &&
                [dict get [$replica memory stats] db.dict.rehashing.count] == 0
            } else {
                fail "hash tables still rehashing on primary/replica"
            }

            set pseed [$primary config get db-hash-seed]
            set rseed [$replica config get db-hash-seed]
            assert_equal $pseed $rseed

            set pkeys [full_scan_keys $primary "k:"]
            set rkeys [full_scan_keys $replica "k:"]

            assert_equal [$primary dbsize] [llength $pkeys]
            assert_equal [$replica  dbsize] [llength $rkeys]
            assert_equal [llength $pkeys] [llength $rkeys]
            assert_equal $pkeys $rkeys
        }
    }
}